from django.db import models

from apps.core.models import TimeStampedModel


class Notification(TimeStampedModel):
    class Channel(models.TextChoices):
        IN_APP = "in_app", "In-app"
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"
        VOICE = "voice", "Voice call"
        WEBHOOK = "webhook", "Webhook"

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
    # Set while a worker is sending; see actions.deliver. Lets us talk to SMTP without holding
    # a row lock, yet still send at most once.
    claimed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    # Which paging event this row belongs to for one user: every channel row of one page shares
    # it. `page()` checks it before creating rows, so a user's rules are snapshotted once and a
    # later edit to them can never add rows to a page that already happened.
    page_key = models.CharField(max_length=255, blank=True, default="", db_default="")
    # A step of a personal notification rule that fires later is `pending` until this time. The
    # database is the timer, exactly like escalations: the ETA task is the fast path and the
    # stuck-notification sweep re-drives anything due whose message was lost.
    not_before = models.DateTimeField(null=True, blank=True)
    # The new columns keep a database-level default (or allow NULL) so the previous release, still
    # running during a rolling deploy, can insert rows without knowing they exist (expand step).
    # Where it went, frozen at creation (a phone number or webhook host), so the record stays
    # true after the person changes their contact details.
    destination = models.CharField(max_length=255, blank=True, default="", db_default="")
    rule_snapshot = models.JSONField(default=dict, blank=True, null=True)
    # The carrier/provider's reference and its latest reported state (Twilio status callbacks).
    provider_id = models.CharField(max_length=64, blank=True, default="", db_default="")
    provider_status = models.CharField(max_length=24, blank=True, default="", db_default="")
    delivered_at = models.DateTimeField(null=True, blank=True)

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
            # Both built CONCURRENTLY (migration 0005) so adding them never blocks paging.
            models.Index(fields=["incident", "page_key"], name="notification_page_key_idx"),
            models.Index(
                fields=["provider_id"],
                name="notification_provider_idx",
                condition=~models.Q(provider_id=""),
            ),
        ]

    def __str__(self) -> str:
        return self.idempotency_key


class UserContact(TimeStampedModel):
    """A person's reachable addresses beyond their email. Kept apart from User so secrets
    (webhook signing key, pending verification code) never travel through user serializers."""

    user = models.OneToOneField("accounts.User", on_delete=models.CASCADE, related_name="contact")
    phone_number = models.CharField(max_length=20, blank=True)  # E.164
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    # Verification code: only an HMAC is stored, with an expiry and an attempt budget.
    phone_code_hash = models.CharField(max_length=64, blank=True)
    phone_code_expires_at = models.DateTimeField(null=True, blank=True)
    phone_code_attempts = models.PositiveSmallIntegerField(default=0)
    webhook_url = models.CharField(max_length=500, blank=True)
    # Needed in the clear to sign requests; write-only through the API.
    webhook_secret = models.CharField(max_length=64, blank=True)

    def __str__(self) -> str:
        return f"contact for user {self.user_id}"

    @property
    def phone_verified(self) -> bool:
        return bool(self.phone_number) and self.phone_verified_at is not None


class NotificationRule(TimeStampedModel):
    """One step of a person's own paging plan: "after N minutes, if still unanswered, use X".

    With no rules a person gets the default (inbox + email, immediately). With rules, the
    inbox entry is still always created and these steps decide everything else. Steps are
    snapshotted onto Notification rows when a page happens (see notifications/actions.py).
    """

    class Urgency(models.TextChoices):
        ANY = "any", "Any urgency"
        HIGH = "high", "High urgency only"
        LOW = "low", "Low urgency only"

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="notification_rules"
    )
    position = models.PositiveSmallIntegerField()  # creation order; tie-break and step number
    channel = models.CharField(
        max_length=16,
        choices=[
            (Notification.Channel.EMAIL, "Email"),
            (Notification.Channel.SMS, "SMS"),
            (Notification.Channel.VOICE, "Voice call"),
            (Notification.Channel.WEBHOOK, "Webhook"),
        ],
    )
    delay_minutes = models.PositiveSmallIntegerField(default=0)
    urgency = models.CharField(max_length=8, choices=Urgency.choices, default=Urgency.ANY)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["delay_minutes", "position"]
        constraints = [
            models.UniqueConstraint(fields=["user", "position"], name="uniq_rule_position"),
            models.CheckConstraint(
                condition=models.Q(delay_minutes__lte=1440), name="rule_delay_at_most_a_day"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.channel} after {self.delay_minutes}m"


class ActionLink(TimeStampedModel):
    """A one-time capability to acknowledge or resolve one incident, carried in a page.

    The URL holds an unguessable id plus an HMAC; this row is the authority: it expires, and it
    can be spent exactly once (an atomic `UPDATE ... WHERE used_at IS NULL`). Opening the link is
    harmless (it only shows a confirmation); only the POST from that page spends it, so mail
    scanners and SMS previewers that fetch URLs cannot acknowledge anything.
    """

    class Action(models.TextChoices):
        ACK = "ack", "Acknowledge"
        RESOLVE = "resolve", "Resolve"

    jti = models.CharField(max_length=32, unique=True)
    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE, related_name="action_links"
    )
    action = models.CharField(max_length=8, choices=Action.choices)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.action} link for notification {self.notification_id}"
