from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class EscalationPolicy(models.Model):
    """
    Tiered operational escalation policy owned by a Team.
    Defines sequential escalation levels for unacknowledged incidents.
    """

    name = models.CharField(max_length=128)
    slug = models.SlugField(max_length=128, unique=True)
    team = models.ForeignKey(
        "users.Team",
        on_delete=models.PROTECT,
        related_name="escalation_policies",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Escalation Policy"
        verbose_name_plural = "Escalation Policies"

    def __str__(self) -> str:
        return f"{self.name} ({self.team.name})"


class EscalationLevel(models.Model):
    """
    Individual step in an EscalationPolicy.
    Specifies the target to page and wait duration before escalating to the next level.
    """

    class TargetType(models.TextChoices):
        CURRENT_ON_CALL = "CURRENT_ON_CALL", "Current On-Call"
        USER = "USER", "User"

    policy = models.ForeignKey(
        EscalationPolicy,
        on_delete=models.CASCADE,
        related_name="levels",
    )
    order = models.PositiveIntegerField(
        help_text="1-based sequence order within the escalation policy."
    )
    target_type = models.CharField(
        max_length=32,
        choices=TargetType.choices,
        default=TargetType.CURRENT_ON_CALL,
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="escalation_levels",
        help_text="Target user when target_type is USER.",
    )
    wait_minutes = models.PositiveIntegerField(
        default=15,
        help_text="Minutes to wait after notifying this level before escalating to the next.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order"]
        verbose_name = "Escalation Level"
        verbose_name_plural = "Escalation Levels"
        constraints = [
            models.UniqueConstraint(
                fields=["policy", "order"],
                name="unique_policy_level_order",
            )
        ]

    def clean(self) -> None:
        super().clean()
        if self.order is not None and self.order < 1:
            raise ValidationError({"order": "Order must be a positive integer starting at 1."})

        if self.wait_minutes is not None and self.wait_minutes < 0:
            raise ValidationError({"wait_minutes": "Wait minutes must be non-negative."})

        if self.target_type == self.TargetType.USER:
            if not self.target_user:
                raise ValidationError({"target_user": "Target user is required when target_type is USER."})
            if not self.target_user.is_active:
                raise ValidationError({"target_user": "Target user must be active."})
            if self.policy_id and self.policy.team_id:
                from apps.users.models import TeamMembership

                is_member = TeamMembership.objects.filter(
                    team=self.policy.team,
                    user=self.target_user,
                    is_active=True,
                ).exists()
                if not is_member:
                    raise ValidationError(
                        {"target_user": f"User {self.target_user.username} is not an active member of team {self.policy.team.name}."}
                    )
        elif self.target_type == self.TargetType.CURRENT_ON_CALL:
            if self.target_user is not None:
                raise ValidationError({"target_user": "Target user must be null when target_type is CURRENT_ON_CALL."})

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.policy.name} - Level {self.order} ({self.target_type})"
