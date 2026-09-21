from django.conf import settings
from django.db import models


class Notification(models.Model):
    """
    Durable, audit-trailed notification record representing an alert dispatch to a responder.
    Guarantees idempotency via unique dedupe_key.
    """

    class Channel(models.TextChoices):
        EMAIL = "EMAIL", "Email"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"

    incident = models.ForeignKey(
        "incidents.Incident",
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="notifications",
    )
    channel = models.CharField(
        max_length=32,
        choices=Channel.choices,
        default=Channel.EMAIL,
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING,
    )
    escalation_level = models.ForeignKey(
        "escalation.EscalationLevel",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="notifications",
    )
    dedupe_key = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Deterministic idempotency token preventing duplicate notifications.",
    )
    attempt_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of delivery attempts made.",
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        indexes = [
            models.Index(fields=["incident", "recipient", "status"]),
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return f"Notification {self.id} [{self.channel} -> {self.recipient.username}] ({self.status})"
