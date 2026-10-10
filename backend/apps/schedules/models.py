from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel
from apps.core.validators import validate_timezone


class Rotation(models.TextChoices):
    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"
    # Fixed-length turns measured in absolute hours (e.g. 12h follow-the-sun).
    CUSTOM = "custom", "Custom"


class Schedule(TimeStampedModel):
    team = models.ForeignKey("accounts.Team", on_delete=models.CASCADE, related_name="schedules")
    name = models.CharField(max_length=120)
    # Rotation maths happens in this zone, so a 09:00 handoff stays 09:00 across DST.
    timezone = models.CharField(max_length=64, default="UTC", validators=[validate_timezone])

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ScheduleLayer(TimeStampedModel):
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name="layers")
    name = models.CharField(max_length=120)
    # Higher priority wins when several layers have someone on call.
    priority = models.PositiveSmallIntegerField(default=0)
    rotation_type = models.CharField(max_length=16, choices=Rotation.choices)
    # Days (daily) or weeks (weekly) per person's turn. Unused for custom rotations.
    turn_count = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    # Turn length for custom rotations only.
    turn_length = models.DurationField(null=True, blank=True)
    start = models.DateTimeField()
    handoff_time = models.TimeField()

    class Meta:
        ordering = ["schedule", "-priority"]
        constraints = [
            models.UniqueConstraint(
                fields=["schedule", "priority"], name="uniq_layer_schedule_priority"
            ),
            models.CheckConstraint(
                condition=models.Q(turn_count__gte=1), name="layer_turn_count_min_1"
            ),
            models.CheckConstraint(
                condition=~models.Q(rotation_type="custom") | models.Q(turn_length__isnull=False),
                name="layer_custom_needs_turn_length",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.schedule} / {self.name}"


class LayerMember(TimeStampedModel):
    layer = models.ForeignKey(ScheduleLayer, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="+")
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["layer", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["layer", "position"], name="uniq_member_layer_position"
            ),
        ]


class ScheduleOverride(TimeStampedModel):
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name="overrides")
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="+")
    start = models.DateTimeField()
    end = models.DateTimeField()

    class Meta:
        ordering = ["schedule", "start"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end__gt=models.F("start")), name="override_end_after_start"
            ),
        ]
        indexes = [models.Index(fields=["schedule", "start", "end"], name="override_window_idx")]
