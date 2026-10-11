"""Signed, expiring, single-use acknowledge/resolve links.

    https://pulse.example/a/<token>/

The token is `base64url(jti[16] | expiry[4] | action[1] | mac[12])`. The HMAC lets a forged or
mangled link be rejected without touching the database; the `ActionLink` row is the authority
(it must exist, be unexpired, and be spent exactly once). The key is derived from SECRET_KEY
with a purpose label, so it is not the raw secret and cannot be confused with other signatures.
"""

import base64
import hashlib
import hmac
import secrets
import struct
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import ActionLink, Notification

_ACTION_CODE: dict[str, int] = {ActionLink.Action.ACK: 1, ActionLink.Action.RESOLVE: 2}
_CODE_ACTION: dict[int, str] = {v: k for k, v in _ACTION_CODE.items()}
_MAC_BYTES = 12


class InvalidLink(Exception):
    """Malformed, forged, unknown, expired or already used. Deliberately one error: the page
    never tells a prober which of those it was."""


@dataclass(frozen=True)
class Parsed:
    jti: str
    action: str
    expires_at: datetime


def _key() -> bytes:
    return hmac.new(settings.SECRET_KEY.encode(), b"pulse.action-link.v1", hashlib.sha256).digest()


def _mac(jti: bytes, expiry: int, code: int) -> bytes:
    message = jti + struct.pack(">IB", expiry, code)
    return hmac.new(_key(), message, hashlib.sha256).digest()[:_MAC_BYTES]


def issue(notification: Notification, action: str, *, now: datetime | None = None) -> str:
    """Create the link row and return its URL path component (the token)."""
    now = now or timezone.now()
    expires_at = now + timedelta(hours=settings.ACTION_LINK_TTL_HOURS)
    raw = secrets.token_bytes(16)
    ActionLink.objects.create(
        jti=raw.hex(), notification=notification, action=action, expires_at=expires_at
    )
    expiry = int(expires_at.timestamp())
    payload = (
        raw
        + struct.pack(">IB", expiry, _ACTION_CODE[action])
        + _mac(raw, expiry, _ACTION_CODE[action])
    )
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode()


def url_for(token: str) -> str:
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/a/{token}/"


def parse(token: str) -> Parsed:
    """Verify the signature. Raises InvalidLink; touches no database."""
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    except (ValueError, TypeError) as exc:
        raise InvalidLink from exc
    if len(raw) != 16 + 5 + _MAC_BYTES:
        raise InvalidLink
    jti, rest, mac = raw[:16], raw[16:21], raw[21:]
    expiry, code = struct.unpack(">IB", rest)
    if code not in _CODE_ACTION or not hmac.compare_digest(mac, _mac(jti, expiry, code)):
        raise InvalidLink
    return Parsed(jti.hex(), _CODE_ACTION[code], datetime.fromtimestamp(expiry, tz=UTC))


def load(token: str, *, now: datetime | None = None) -> ActionLink:
    """The live link row for a token, without spending it (for the confirmation page)."""
    now = now or timezone.now()
    parsed = parse(token)
    link = (
        ActionLink.objects.select_related("notification__incident__service", "notification__user")
        .filter(jti=parsed.jti, action=parsed.action)
        .first()
    )
    if link is None or link.used_at is not None or link.expires_at <= now:
        raise InvalidLink
    return link


def spend(token: str, *, now: datetime | None = None) -> ActionLink:
    """Atomically mark the link used. Exactly one concurrent caller gets it; the rest fail.

    Call inside the transaction that performs the action, so a failed action gives the link back.
    """
    now = now or timezone.now()
    parsed = parse(token)
    with transaction.atomic():
        won = ActionLink.objects.filter(
            jti=parsed.jti, action=parsed.action, used_at__isnull=True, expires_at__gt=now
        ).update(used_at=now)
        if not won:
            raise InvalidLink
        return ActionLink.objects.select_related(
            "notification__incident__service", "notification__user"
        ).get(jti=parsed.jti)
