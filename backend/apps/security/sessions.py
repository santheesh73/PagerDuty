"""Track sessions per user so they can be listed and revoked."""

from typing import Any

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.sessions.models import Session
from django.dispatch import receiver
from django.http import HttpRequest

from .audit import _ip
from .models import SessionRecord


@receiver(user_logged_in)
def _remember(sender: Any, request: HttpRequest | None, user: Any, **_: Any) -> None:
    if request is None or not request.session.session_key:
        return
    SessionRecord.objects.update_or_create(
        session_key=request.session.session_key,
        defaults={
            "user": user,
            "ip": _ip(request),
            "user_agent": request.headers.get("User-Agent", "")[:200],
        },
    )


@receiver(user_logged_out)
def _forget(sender: Any, request: HttpRequest | None, user: Any, **_: Any) -> None:
    if request is not None and request.session.session_key:
        SessionRecord.objects.filter(session_key=request.session.session_key).delete()


def revoke(user: Any, *, keep: str | None = None) -> int:
    """End every session of `user` except `keep`. Returns how many were ended."""
    records = SessionRecord.objects.filter(user=user)
    if keep:
        records = records.exclude(session_key=keep)
    keys = list(records.values_list("session_key", flat=True))
    Session.objects.filter(session_key__in=keys).delete()
    records.delete()
    return len(keys)
