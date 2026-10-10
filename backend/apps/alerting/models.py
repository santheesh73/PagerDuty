from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class Severity(models.TextChoices):
    CRITICAL = "critical", "Critical"
    ERROR = "error", "Error"
    WARNING = "warning", "Warning"
    INFO = "info", "Info"


class Alert(TimeStampedModel):
    """One raw signal from a monitoring system. Many alerts can roll up into one incident."""

    class Status(models.TextChoices):
        TRIGGERED = "triggered", "Triggered"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        RESOLVED = "resolved", "Resolved"
        SUPPRESSED = "suppressed", "Suppressed"

    service = models.ForeignKey("catalog.Service", on_delete=models.CASCADE, related_name="alerts")
    incident = models.ForeignKey(
        "incidents.Incident",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alerts",
    )
    dedup_key = models.CharField(max_length=255)
    severity = models.CharField(max_length=16, choices=Severity.choices)
    summary = models.CharField(max_length=1024)
    source = models.CharField(max_length=255, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.TRIGGERED)
    received_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-received_at"]
        indexes = [models.Index(fields=["service", "dedup_key"], name="alert_service_dedup_idx")]

    def __str__(self) -> str:
        return self.summary
