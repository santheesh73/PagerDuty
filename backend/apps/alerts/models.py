from django.db import models
from django.utils import timezone


class Alert(models.Model):
    """
    Normalized operational signal emitted by external monitors or engineers.
    Serves as the raw event foundation for Phase 3 incident triage and deduplication.
    """

    class Severity(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"
        CRITICAL = "CRITICAL", "Critical"

    service = models.ForeignKey(
        "services.Service",
        on_delete=models.CASCADE,
        related_name="alerts",
    )
    incident = models.ForeignKey(
        "incidents.Incident",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alerts",
    )
    severity = models.CharField(
        max_length=32,
        choices=Severity.choices,
        default=Severity.LOW,
    )
    message = models.TextField()
    source = models.CharField(max_length=64)
    fingerprint = models.CharField(max_length=64, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    received_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at"]
        verbose_name = "Alert"
        verbose_name_plural = "Alerts"

    def __str__(self) -> str:
        return f"[{self.severity}] {self.service.name}: {self.message[:50]}"
