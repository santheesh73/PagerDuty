from django.db import models
from django.db.models.expressions import Func, Value

from apps.core.models import TimeStampedModel

INCIDENT_NUMBER_SEQUENCE = "incidents_incident_number_seq"


class NextVal(Func):
    """`nextval('<sequence>')` — a race-free, human-friendly incident number from Postgres."""

    function = "nextval"
    output_field = models.BigIntegerField()

    def __init__(self, sequence: str) -> None:
        super().__init__(Value(sequence))


class Status(models.TextChoices):
    TRIGGERED = "triggered", "Triggered"
    ACKNOWLEDGED = "acknowledged", "Acknowledged"
    RESOLVED = "resolved", "Resolved"


class Urgency(models.TextChoices):
    HIGH = "high", "High"
    LOW = "low", "Low"


class EventType(models.TextChoices):
    TRIGGERED = "triggered"
    ALERT_ATTACHED = "alert_attached"
    ACKNOWLEDGED = "acknowledged"
    UNACKNOWLEDGED = "unacknowledged"
    RESOLVED = "resolved"
    REASSIGNED = "reassigned"
    ESCALATED = "escalated"
    MANUAL_ESCALATED = "manual_escalated"
    NO_RESPONDER = "no_responder"
    ESCALATION_EXHAUSTED = "escalation_exhausted"
    NOTE_ADDED = "note_added"
    NOTIFIED = "notified"
    NOTIFICATION_FAILED = "notification_failed"
    MAINTENANCE_STARTED = "maintenance_started"
    MAINTENANCE_ENDED = "maintenance_ended"


class Incident(TimeStampedModel):
    number = models.BigIntegerField(
        unique=True, editable=False, db_default=NextVal(INCIDENT_NUMBER_SEQUENCE)
    )
    service = models.ForeignKey(
        "catalog.Service", on_delete=models.CASCADE, related_name="incidents"
    )
    title = models.CharField(max_length=1024)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.TRIGGERED)
    urgency = models.CharField(max_length=8, choices=Urgency.choices, default=Urgency.HIGH)
    assignee = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_incidents",
    )
    dedup_key = models.CharField(max_length=255)
    is_maintenance = models.BooleanField(default=False)

    # Policy structure frozen at open time; editing the live policy never changes an
    # incident already in flight. See escalations/snapshot.py for the format.
    escalation_snapshot = models.JSONField(default=dict)
    escalation_level = models.PositiveSmallIntegerField(default=0)
    escalation_loop = models.PositiveSmallIntegerField(default=0)
    # The database is the timer: whoever observes now >= next_escalation_at may escalate.
    next_escalation_at = models.DateTimeField(null=True, blank=True)

    triggered_at = models.DateTimeField()
    first_response_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    alert_count = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-triggered_at"]
        constraints = [
            # The real dedup guarantee: at most one open incident per (service, dedup_key).
            # Concurrent triggers race here and the loser retries as an attach.
            models.UniqueConstraint(
                fields=["service", "dedup_key"],
                condition=~models.Q(status=Status.RESOLVED),
                name="uniq_open_incident_per_dedup_key",
            ),
        ]
        indexes = [
            models.Index(
                fields=["status", "next_escalation_at"], name="incident_due_escalation_idx"
            ),
            models.Index(fields=["service", "triggered_at"], name="incident_service_time_idx"),
            # The incident list's order (newest first, id breaks ties) without a sort: the SPA polls
            # it, and 300k rows took 128 ms per request in the final audit.
            models.Index(fields=["-triggered_at", "-id"], name="incident_list_order_idx"),
        ]

    def __str__(self) -> str:
        return f"#{self.number} {self.title}"

    @property
    def is_open(self) -> bool:
        return self.status != Status.RESOLVED


class IncidentEvent(TimeStampedModel):
    """Append-only timeline. `actor` is null when the system acted."""

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="events")
    type = models.CharField(max_length=32, choices=EventType.choices)
    actor = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    message = models.TextField(blank=True)
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["incident", "created_at"], name="event_incident_time_idx")]

    def __str__(self) -> str:
        return f"{self.incident_id}:{self.type}"
