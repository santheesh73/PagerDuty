from django.db import models

from apps.core.models import TimeStampedModel


class Notification(TimeStampedModel):
    class Channel(models.TextChoices):
        IN_APP = "in_app", "In-app"
        EMAIL = "email", "Email"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        DRY_RUN = "dry_run", "Dry run"
        CANCELLED = "cancelled", "Cancelled"  # incident resolved before it was delivered

    incident = models.ForeignKey(
        "incidents.Incident", on_delete=models.CASCADE, related_name="notifications"
    )
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="notifications"
    )
    channel = models.CharField(max_length=16, choices=Channel.choices)
    # incident:{id}:level:{n}:loop:{k}:user:{id}:channel:{c}[:seq:{event_id}]
    # Unique in Postgres, so a retried or double-fired page can never create a second row.
    idempotency_key = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "read_at"], name="notification_inbox_idx"),
            # sweep_stuck_notifications only ever looks at pending rows.
            models.Index(
                fields=["created_at"],
                name="notification_pending_idx",
                condition=models.Q(status="pending"),
            ),
        ]

    def __str__(self) -> str:
        return self.idempotency_key
