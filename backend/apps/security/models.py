from django.db import models

from apps.core.models import TimeStampedModel


class MfaDevice(TimeStampedModel):
    """One TOTP authenticator per person. Unconfirmed until a code from it has been entered."""

    user = models.OneToOneField("accounts.User", on_delete=models.CASCADE, related_name="mfa")
    # Needed in the clear to compute codes (TOTP is symmetric). Never returned after setup.
    secret = models.CharField(max_length=64)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    # The last time step accepted; a code for this step or an earlier one is refused (replay).
    last_used_step = models.BigIntegerField(default=0)

    def __str__(self) -> str:
        return f"MFA for user {self.user_id}"

    @property
    def enabled(self) -> bool:
        return self.confirmed_at is not None


class BackupCode(TimeStampedModel):
    """Single-use recovery codes. Only a keyed hash is stored."""

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="backup_codes")
    code_hash = models.CharField(max_length=64, unique=True)
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"backup code for user {self.user_id}"


class SessionRecord(models.Model):
    """Which sessions belong to whom, so a person can see and revoke theirs ("log out everywhere")
    and a password reset can end every session at once."""

    session_key = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="session_records"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)

    def __str__(self) -> str:
        return f"session of user {self.user_id}"


class AuditEvent(models.Model):
    """Append-only record of security-relevant actions.

    No foreign keys on purpose: the record must outlive the user, team or service it mentions, and
    an ON DELETE SET NULL would be an UPDATE, which the database trigger in migration 0001 refuses.
    UPDATE and DELETE are rejected by Postgres itself, not just by this model, so neither the app,
    the admin nor a SQL injection through the app's role can rewrite history.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    action = models.CharField(max_length=64, db_index=True)
    actor_id = models.BigIntegerField(null=True, blank=True)
    actor_email = models.CharField(max_length=254, blank=True)
    team_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    target_type = models.CharField(max_length=40, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.action} by {self.actor_email or 'system'}"

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise RuntimeError("audit events are append-only")
        super().save(*args, **kwargs)  # type: ignore[arg-type,unused-ignore]

    def delete(self, *args: object, **kwargs: object) -> tuple[int, dict[str, int]]:
        raise RuntimeError("audit events are append-only")
