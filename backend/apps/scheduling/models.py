import zoneinfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Schedule(models.Model):
    """
    On-call schedule owned by an operational Team.
    A team may have multiple schedules, but at most ONE active primary schedule used for routing.
    """

    name = models.CharField(max_length=128)
    slug = models.SlugField(max_length=128, unique=True)
    team = models.ForeignKey(
        "users.Team",
        on_delete=models.CASCADE,
        related_name="schedules",
    )
    timezone = models.CharField(max_length=64, default="UTC")
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Schedule"
        verbose_name_plural = "Schedules"
        constraints = [
            models.UniqueConstraint(
                fields=["team"],
                condition=models.Q(is_primary=True, is_active=True),
                name="unique_active_primary_schedule_per_team",
            )
        ]

    def __str__(self) -> str:
        primary_suffix = " (Primary)" if self.is_primary else ""
        return f"{self.name}{primary_suffix} [{self.team.name}]"

    def clean(self):
        super().clean()
        if self.timezone:
            valid_timezones = zoneinfo.available_timezones()
            if self.timezone not in valid_timezones:
                raise ValidationError({"timezone": f"Invalid timezone '{self.timezone}'."})
        if self.team_id and not self.team.is_active and self.is_active:
            raise ValidationError({"team": "Cannot create or activate a schedule for an inactive team."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ScheduleRotation(models.Model):
    """
    Concrete on-call shift window assigned to an active team member.
    Operates on half-open intervals: start_time <= timestamp < end_time.
    Supports overrides that take precedence over base rotations.
    """

    schedule = models.ForeignKey(
        "scheduling.Schedule",
        on_delete=models.CASCADE,
        related_name="rotations",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="schedule_rotations",
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    is_override = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_time", "id"]
        verbose_name = "Schedule Rotation"
        verbose_name_plural = "Schedule Rotations"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="rotation_end_time_after_start_time",
            )
        ]
        indexes = [
            models.Index(fields=["schedule", "start_time", "end_time"]),
            models.Index(fields=["schedule", "is_override"]),
        ]

    def __str__(self) -> str:
        kind = "OVERRIDE" if self.is_override else "BASE"
        return f"[{kind}] {self.user.username}: {self.start_time.isoformat()} -> {self.end_time.isoformat()}"

    def clean(self):
        super().clean()
        from django.utils import timezone

        from apps.scheduling.exceptions import (
            IneligibleUserError,
            InvalidTimestampError,
            RotationOverlapError,
        )

        if self.start_time and timezone.is_naive(self.start_time):
            raise InvalidTimestampError("Rotation start_time must be timezone-aware.")
        if self.end_time and timezone.is_naive(self.end_time):
            raise InvalidTimestampError("Rotation end_time must be timezone-aware.")

        if self.start_time and self.end_time:
            if self.end_time <= self.start_time:
                raise ValidationError({"end_time": "Rotation end_time must be strictly after start_time."})

        # User eligibility validation
        if self.schedule_id and self.user_id:
            from apps.users.models import TeamMembership

            if not self.user.is_active:
                err = IneligibleUserError({"user": f"User '{self.user.username}' is inactive."})
                self._domain_error = err
                raise err

            is_active_member = TeamMembership.objects.filter(
                team=self.schedule.team,
                user=self.user,
                is_active=True,
            ).exists()
            if not is_active_member:
                err = IneligibleUserError({
                    "user": f"User '{self.user.username}' is not an active member of team '{self.schedule.team.name}'."
                })
                self._domain_error = err
                raise err

            # Overlap validation:
            # Base cannot overlap with Base; Override cannot overlap with Override.
            if self.start_time and self.end_time:
                overlap_qs = ScheduleRotation.objects.filter(
                    schedule=self.schedule,
                    is_override=self.is_override,
                    start_time__lt=self.end_time,
                    end_time__gt=self.start_time,
                )
                if self.pk:
                    overlap_qs = overlap_qs.exclude(pk=self.pk)

                if overlap_qs.exists():
                    rotation_type = "Override" if self.is_override else "Base"
                    err = RotationOverlapError(
                        f"{rotation_type} rotation overlaps with an existing {rotation_type.lower()} rotation on this schedule."
                    )
                    self._domain_error = err
                    raise err

    def save(self, *args, **kwargs):
        try:
            self.full_clean()
        except ValidationError as exc:
            if getattr(self, "_domain_error", None):
                domain_err = self._domain_error
                self._domain_error = None
                raise domain_err
            raise exc
        super().save(*args, **kwargs)

