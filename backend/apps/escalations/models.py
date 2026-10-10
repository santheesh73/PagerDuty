from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel


class EscalationPolicy(TimeStampedModel):
    team = models.ForeignKey(
        "accounts.Team", on_delete=models.CASCADE, related_name="escalation_policies"
    )
    name = models.CharField(max_length=120)
    num_loops = models.PositiveSmallIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(3)]
    )

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "escalation policies"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(num_loops__lte=3), name="policy_num_loops_max_3"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class EscalationRule(TimeStampedModel):
    """One level of a policy. Who gets paged at this level lives in EscalationTarget."""

    policy = models.ForeignKey(EscalationPolicy, on_delete=models.CASCADE, related_name="rules")
    level = models.PositiveSmallIntegerField()
    delay_minutes = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        ordering = ["policy", "level"]
        constraints = [
            models.UniqueConstraint(fields=["policy", "level"], name="uniq_rule_policy_level"),
            models.CheckConstraint(
                condition=models.Q(delay_minutes__gte=1), name="rule_delay_at_least_1_minute"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.policy} L{self.level}"


class EscalationTarget(TimeStampedModel):
    class Kind(models.TextChoices):
        USER = "user", "User"
        SCHEDULE = "schedule", "Schedule"

    rule = models.ForeignKey(EscalationRule, on_delete=models.CASCADE, related_name="targets")
    position = models.PositiveSmallIntegerField(default=0)
    target_user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    target_schedule = models.ForeignKey(
        "schedules.Schedule", null=True, blank=True, on_delete=models.RESTRICT, related_name="+"
    )

    class Meta:
        ordering = ["rule", "position"]
        constraints = [
            # Exactly one of user / schedule — enforced by Postgres, not just the serializer.
            models.CheckConstraint(
                condition=(
                    models.Q(target_user__isnull=False, target_schedule__isnull=True)
                    | models.Q(target_user__isnull=True, target_schedule__isnull=False)
                ),
                name="target_exactly_one_of_user_or_schedule",
            ),
            models.UniqueConstraint(fields=["rule", "position"], name="uniq_target_rule_position"),
        ]

    @property
    def kind(self) -> str:
        return self.Kind.USER if self.target_user_id else self.Kind.SCHEDULE

    @property
    def target_id(self) -> int:
        return self.target_user_id or self.target_schedule_id  # type: ignore[return-value]
