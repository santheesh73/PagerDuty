import secrets

from django.db import models

from apps.core.models import TimeStampedModel


def generate_integration_key() -> str:
    """32 random bytes, hex-encoded. Possession of this key is the Events API's only auth."""
    return secrets.token_hex(32)


class Service(TimeStampedModel):
    class Mode(models.TextChoices):
        ACTIVE = "active", "Active"
        # All alerts fold into one quiet incident; nobody is paged.
        MAINTENANCE = "maintenance", "Maintenance"
        # Full pipeline runs, but notifications are recorded as dry runs and never sent.
        DEBUG = "debug", "Debug"

    team = models.ForeignKey("accounts.Team", on_delete=models.CASCADE, related_name="services")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    escalation_policy = models.ForeignKey(
        "escalations.EscalationPolicy", on_delete=models.RESTRICT, related_name="services"
    )
    integration_key = models.CharField(
        max_length=64, unique=True, default=generate_integration_key, editable=False
    )
    mode = models.CharField(max_length=16, choices=Mode.choices, default=Mode.ACTIVE)
    mode_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            # expire_service_modes scans only services with a pending expiry.
            models.Index(
                fields=["mode_until"],
                name="service_mode_expiry_idx",
                condition=models.Q(mode_until__isnull=False),
            ),
        ]

    def __str__(self) -> str:
        return self.name
