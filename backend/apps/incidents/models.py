from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Incident(models.Model):
    """
    Core operational incident representing an ongoing or historical production outage.
    Created and grouped deterministically by alert triage.
    """

    class Status(models.TextChoices):
        TRIGGERED = "TRIGGERED", "Triggered"
        ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged"
        RESOLVED = "RESOLVED", "Resolved"

    class Severity(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"
        CRITICAL = "CRITICAL", "Critical"

    service = models.ForeignKey(
        "services.Service",
        on_delete=models.CASCADE,
        related_name="incidents",
    )
    title = models.CharField(max_length=255)
    severity = models.CharField(
        max_length=32,
        choices=Severity.choices,
        default=Severity.LOW,
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.TRIGGERED,
    )
    fingerprint = models.CharField(max_length=64, db_index=True)
    assigned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_incidents",
    )
    current_escalation_level = models.ForeignKey(
        "escalation.EscalationLevel",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="incidents",
    )
    automation_generation = models.PositiveIntegerField(
        default=1,
        help_text="Lifecycle version incremented on reopen to invalidate stale asynchronous automation tasks.",
    )
    triggered_at = models.DateTimeField(default=timezone.now)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-triggered_at"]
        verbose_name = "Incident"
        verbose_name_plural = "Incidents"
        constraints = [
            models.UniqueConstraint(
                fields=["service", "fingerprint"],
                condition=models.Q(resolved_at__isnull=True),
                name="unique_active_incident_service_fingerprint",
            )
        ]
        indexes = [
            models.Index(fields=["service", "fingerprint"]),
            models.Index(fields=["status"]),
            models.Index(fields=["triggered_at"]),
            models.Index(fields=["resolved_at"]),
            models.Index(fields=["current_escalation_level"]),
        ]

    def __str__(self) -> str:
        return f"INC-{self.id}: {self.title} [{self.status}]"


class IncidentEvent(models.Model):
    """
    Immutable audit timeline entry capturing lifecycle transitions and alert attachments.
    Append-only by design.
    """

    class EventType(models.TextChoices):
        INCIDENT_TRIGGERED = "INCIDENT_TRIGGERED", "Incident Triggered"
        ALERT_ATTACHED = "ALERT_ATTACHED", "Alert Attached"
        RESPONDER_ASSIGNED = "RESPONDER_ASSIGNED", "Responder Assigned"
        ROUTING_UNAVAILABLE = "ROUTING_UNAVAILABLE", "Routing Unavailable"
        INCIDENT_ACKNOWLEDGED = "INCIDENT_ACKNOWLEDGED", "Incident Acknowledged"
        INCIDENT_RESOLVED = "INCIDENT_RESOLVED", "Incident Resolved"
        INCIDENT_REOPENED = "INCIDENT_REOPENED", "Incident Reopened"
        ESCALATION_STARTED = "ESCALATION_STARTED", "Escalation Started"
        INCIDENT_ESCALATED = "INCIDENT_ESCALATED", "Incident Escalated"
        ESCALATION_EXHAUSTED = "ESCALATION_EXHAUSTED", "Escalation Exhausted"
        ESCALATION_TARGET_UNAVAILABLE = "ESCALATION_TARGET_UNAVAILABLE", "Escalation Target Unavailable"

    incident = models.ForeignKey(
        "incidents.Incident",
        on_delete=models.PROTECT,
        related_name="events",
    )
    event_type = models.CharField(
        max_length=64,
        choices=EventType.choices,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="incident_events",
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "Incident Event"
        verbose_name_plural = "Incident Events"
        indexes = [
            models.Index(fields=["incident", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"[{self.created_at.isoformat()}] {self.incident_id} - {self.event_type}"

    def save(self, *args, **kwargs):
        if self.pk and IncidentEvent.objects.filter(pk=self.pk).exists():
            raise ValidationError("IncidentEvent is append-only and cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("IncidentEvent is append-only and cannot be deleted.")
