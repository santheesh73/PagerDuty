import hashlib
import secrets
from datetime import datetime, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


def generate_integration_key() -> str:
    """32 random bytes, hex-encoded. Possession of this key is the Events API's only auth."""
    return secrets.token_hex(32)


def hash_integration_key(key: str) -> str:
    """SHA-256 is enough here: keys are 256 random bits, so there is nothing to brute-force, and
    an unkeyed hash keeps working if SECRET_KEY is rotated."""
    return hashlib.sha256(key.encode()).hexdigest()


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
    # Only a hash is stored: a database dump or a read-only SQL injection no longer hands out
    # working credentials. The key itself is shown once, when it is issued.
    # NULL rather than "" while unset, so the unique constraint cannot collide (DJ001 is about
    # two empty values meaning the same thing; here only one is ever possible).
    integration_key_hash = models.CharField(  # noqa: DJ001
        max_length=64, unique=True, null=True, editable=False
    )
    integration_key_prefix = models.CharField(
        max_length=12, blank=True, default="", db_default="", editable=False
    )
    # After a rotation the old key keeps working for a grace window, so monitoring configs can be
    # updated without dropping alerts in between.
    previous_key_hash = models.CharField(
        max_length=64, blank=True, default="", db_default="", editable=False
    )
    previous_key_expires_at = models.DateTimeField(null=True, blank=True, editable=False)
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

    # The plaintext key, only on the instance that just issued it (never loaded from the database).
    integration_key: str | None = None

    def __str__(self) -> str:
        return self.name

    def issue_key(self, *, grace: timedelta | None = None, now: datetime | None = None) -> str:
        """Generate a new key, keep the current one valid for `grace`, return the new plaintext."""
        now = now or timezone.now()
        if grace is None:
            grace = timedelta(hours=settings.INTEGRATION_KEY_GRACE_HOURS)
        if self.integration_key_hash and grace > timedelta(0):
            self.previous_key_hash = self.integration_key_hash
            self.previous_key_expires_at = now + grace
        else:
            self.previous_key_hash = ""
            self.previous_key_expires_at = None
        key = generate_integration_key()
        self.integration_key_hash = hash_integration_key(key)
        self.integration_key_prefix = key[:8]
        self.integration_key = key
        return key

    def save(self, *args: object, **kwargs: object) -> None:
        if not self.integration_key_hash:
            self.issue_key(grace=timedelta(0))
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = {
                    *update_fields,
                    "integration_key_hash",
                    "integration_key_prefix",
                }  # type: ignore[misc]
        super().save(*args, **kwargs)  # type: ignore[arg-type]
