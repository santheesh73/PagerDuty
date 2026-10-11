"""MFA: TOTP enrolment, verification with replay protection, and single-use backup codes."""

import hashlib
import hmac
import secrets
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Membership

from . import totp
from .models import BackupCode, MfaDevice

BACKUP_CODES = 10


def _code_hash(user_id: int, code: str) -> str:
    key = hmac.new(settings.SECRET_KEY.encode(), b"pulse.backup-code.v1", hashlib.sha256).digest()
    normalized = code.strip().lower().replace("-", "").replace(" ", "")
    return hmac.new(key, f"{user_id}:{normalized}".encode(), hashlib.sha256).hexdigest()


def is_admin(user: Any) -> bool:
    return (
        bool(user.is_staff)
        or Membership.objects.filter(user=user, role=Membership.Role.ADMIN).exists()
    )


def enabled(user: Any) -> bool:
    return MfaDevice.objects.filter(user=user, confirmed_at__isnull=False).exists()


def required(user: Any) -> bool:
    return bool(settings.REQUIRE_MFA_FOR_ADMINS) and is_admin(user)


def begin_setup(user: Any) -> MfaDevice:
    """A fresh unconfirmed secret. Refused while MFA is on (disable first)."""
    MfaDevice.objects.filter(user=user, confirmed_at__isnull=True).delete()
    return MfaDevice.objects.create(user=user, secret=totp.generate_secret())


def _new_backup_codes(user: Any) -> list[str]:
    BackupCode.objects.filter(user=user).delete()
    codes = [f"{secrets.token_hex(3)}-{secrets.token_hex(3)}" for _ in range(BACKUP_CODES)]
    BackupCode.objects.bulk_create(
        BackupCode(user=user, code_hash=_code_hash(user.pk, code)) for code in codes
    )
    return codes


def confirm(user: Any, code: str) -> list[str] | None:
    """Turn MFA on if `code` matches the pending secret. Returns the backup codes (shown once)."""
    with transaction.atomic():
        device = MfaDevice.objects.select_for_update().filter(user=user).first()
        if device is None or device.enabled:
            return None
        step = totp.verify(device.secret, code, last_step=device.last_used_step)
        if step is None:
            return None
        device.confirmed_at = timezone.now()
        device.last_used_step = step
        device.save(update_fields=["confirmed_at", "last_used_step", "updated_at"])
        return _new_backup_codes(user)


def verify(user: Any, code: str) -> str | None:
    """Check a sign-in code: a TOTP code (each one usable once) or an unused backup code.
    Returns "totp" or "backup" on success, None otherwise."""
    with transaction.atomic():
        device = (
            MfaDevice.objects.select_for_update()
            .filter(user=user, confirmed_at__isnull=False)
            .first()
        )
        if device is None:
            return None
        step = totp.verify(device.secret, code, last_step=device.last_used_step)
        if step is not None:
            device.last_used_step = step
            device.save(update_fields=["last_used_step", "updated_at"])
            return "totp"
        spent = BackupCode.objects.filter(
            user=user, code_hash=_code_hash(user.pk, code), used_at__isnull=True
        ).update(used_at=timezone.now())
        return "backup" if spent else None


def regenerate_backup_codes(user: Any) -> list[str]:
    return _new_backup_codes(user)


def remaining_backup_codes(user: Any) -> int:
    return BackupCode.objects.filter(user=user, used_at__isnull=True).count()


def disable(user: Any) -> None:
    MfaDevice.objects.filter(user=user).delete()
    BackupCode.objects.filter(user=user).delete()
