"""Paging writes. Notification rows are the durable record of "this person must be paged".

They are created inside the caller's transaction (the same one that escalated or opened
the incident), so a page can't be lost between "decided to page" and "enqueued". Delivery
runs afterwards in a task; if the broker drops that message, `sweep_stuck_notifications`
re-drives every row still pending.
"""

import logging
from collections.abc import Iterable
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Service
from apps.core import dispatch
from apps.incidents.models import EventType, Incident, Status
from apps.incidents.timeline import record

from .channels import CHANNELS, PAGE_CHANNELS, ChannelError
from .models import Notification

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
STUCK_AFTER = timedelta(seconds=90)
# How long a worker may hold a notification while sending before another may take over.
# Must stay above EMAIL_TIMEOUT and below STUCK_AFTER, so a dead worker's page is retried by
# the next sweep.
CLAIM_TTL = timedelta(seconds=60)


def idempotency_key(
    incident_id: int, level: int, loop: int, user_id: int, channel: str, seq: int | None = None
) -> str:
    key = f"incident:{incident_id}:level:{level}:loop:{loop}:user:{user_id}:channel:{channel}"
    return f"{key}:seq:{seq}" if seq is not None else key


def page(
    incident: Incident,
    users: Iterable[User],
    *,
    level: int,
    loop: int,
    seq: int | None = None,
) -> list[Notification]:
    """Create (at most once per idempotency key) and dispatch notifications.

    Re-running with the same (incident, level, loop, seq) is a no-op: the unique key makes
    the second `get_or_create` find the first row instead of paging again.
    """
    if incident.is_maintenance:
        return []  # I13: maintenance incidents never page, whatever a human clicks
    dry_run = incident.service.mode == Service.Mode.DEBUG
    created: list[Notification] = []
    for user in users:
        for channel in PAGE_CHANNELS:
            notification, was_created = Notification.objects.get_or_create(
                idempotency_key=idempotency_key(incident.pk, level, loop, user.pk, channel, seq),
                defaults={
                    "incident": incident,
                    "user": user,
                    "channel": channel,
                    "status": Notification.Status.DRY_RUN
                    if dry_run
                    else Notification.Status.PENDING,
                },
            )
            if not was_created:
                continue
            created.append(notification)
            if dry_run:
                record(
                    incident,
                    EventType.NOTIFIED,
                    user_id=user.pk,
                    channel=channel,
                    dry_run=True,
                    message=f"Dry run: would notify {user} via {channel}",
                )
            else:
                from .tasks import deliver_notification

                dispatch.on_commit(deliver_notification, notification.pk)
    return created


def deliver(notification_id: int, *, now: datetime | None = None) -> Notification | None:
    """Send one notification. Safe to call any number of times: only a pending row sends.

    Three short steps so no database lock is held while we wait on SMTP:

    1. *claim* (row locked): apply the guards, count the attempt and stamp `claimed_at`.
       Exactly one concurrent caller wins; the rest see a fresh claim and return.
    2. *send*, with no transaction open.
    3. *settle* (row locked): record sent, or the failure and whether to retry.

    A worker that dies between 1 and 3 leaves a claim that expires after `CLAIM_TTL`; the
    next delivery takes over, and the dead try still counts toward `MAX_ATTEMPTS`.
    """
    now = now or timezone.now()
    notification, claimed = _claim(notification_id, now)
    if not claimed or notification is None:
        return notification

    error: Exception | None = None
    try:
        CHANNELS[notification.channel].send(notification)
    except Exception as exc:
        # Every failure a channel raises must count as an attempt. Catching only
        # ChannelError let anything else (a bad header, an unknown channel key) escape
        # before `attempts` was committed, so MAX_ATTEMPTS could never trip and
        # `redispatch_stuck` re-drove the same poison row every sweep, forever.
        error = exc
        if not isinstance(exc, ChannelError):
            logger.exception(
                "notification channel raised an unexpected error",
                extra={"notification_id": notification.pk, "channel": notification.channel},
            )

    settled = _settle(notification.pk, error, now)
    if settled.status == Notification.Status.PENDING:
        # Fell out of the transaction so the attempt count committed; let Celery retry.
        raise ChannelError(settled.last_error)
    return settled


def _claim(notification_id: int, now: datetime) -> tuple[Notification | None, bool]:
    with transaction.atomic():
        notification = (
            Notification.objects.select_for_update(of=("self",))
            .select_related("incident__service", "user")
            .filter(pk=notification_id)
            .first()
        )
        if notification is None or notification.status != Notification.Status.PENDING:
            return notification, False

        incident = notification.incident
        if incident.status == Status.RESOLVED:
            # C1: the page was queued before the incident closed (broker outage, retries).
            notification.status = Notification.Status.CANCELLED
            notification.save(update_fields=["status", "updated_at"])
            return notification, False
        if incident.service.mode == Service.Mode.DEBUG:
            # Mode switched to debug after the row was created: still never send.
            notification.status = Notification.Status.DRY_RUN
            notification.save(update_fields=["status", "updated_at"])
            return notification, False
        if notification.claimed_at and now - notification.claimed_at < CLAIM_TTL:
            return notification, False  # another worker is sending it right now
        if notification.attempts >= MAX_ATTEMPTS:
            # Earlier workers took their claims and died before settling.
            _fail(notification, "worker died while sending")
            return notification, False

        notification.attempts += 1
        notification.claimed_at = now
        notification.save(update_fields=["attempts", "claimed_at", "updated_at"])
        return notification, True


def _settle(notification_id: int, error: Exception | None, now: datetime) -> Notification:
    with transaction.atomic():
        notification = (
            Notification.objects.select_for_update(of=("self",))
            .select_related("incident", "user")
            .get(pk=notification_id)
        )
        notification.claimed_at = None
        if error is None:
            notification.status = Notification.Status.SENT
            notification.sent_at = now
            notification.save(update_fields=["status", "sent_at", "claimed_at", "updated_at"])
            record(
                notification.incident,
                EventType.NOTIFIED,
                user_id=notification.user_id,
                channel=notification.channel,
                message=(f"Notified {notification.user} via {notification.get_channel_display()}"),
            )
            return notification
        if isinstance(error, ChannelError):
            notification.last_error = str(error)[:2000]
        else:
            # Not a declared transient failure: keep the type so the row says what broke.
            notification.last_error = f"{type(error).__name__}: {error}"[:2000]
        if notification.attempts >= MAX_ATTEMPTS:
            _fail(notification, notification.last_error)
            return notification
        notification.save(update_fields=["last_error", "claimed_at", "updated_at"])
        return notification


def _fail(notification: Notification, reason: str) -> None:
    notification.status = Notification.Status.FAILED
    notification.claimed_at = None
    if not notification.last_error:
        notification.last_error = reason
    notification.save(update_fields=["status", "claimed_at", "last_error", "updated_at"])
    record(
        notification.incident,
        EventType.NOTIFICATION_FAILED,
        user_id=notification.user_id,
        channel=notification.channel,
        attempts=notification.attempts,
        message=f"Could not notify {notification.user} via {notification.channel}",
    )
    logger.error(
        "notification failed permanently",
        extra={"incident_id": notification.incident_id, "notification_id": notification.pk},
    )


def redispatch_stuck(*, now: datetime | None = None, limit: int = 500) -> int:
    """Re-enqueue pending notifications whose task message was lost (e.g. Redis restart)."""
    now = now or timezone.now()
    ids = list(
        Notification.objects.filter(
            status=Notification.Status.PENDING,
            attempts__lt=MAX_ATTEMPTS,
            updated_at__lt=now - STUCK_AFTER,
        ).values_list("pk", flat=True)[:limit]
    )
    from .tasks import deliver_notification

    for pk in ids:
        try:
            deliver_notification.delay(pk)
        except Exception:
            logger.exception("re-dispatch failed", extra={"notification_id": pk})
            break
    return len(ids)


def mark_read(notification: Notification, *, now: datetime | None = None) -> Notification:
    if notification.read_at is None:
        notification.read_at = now or timezone.now()
        notification.save(update_fields=["read_at", "updated_at"])
    return notification


def mark_all_read(user: User, *, now: datetime | None = None) -> int:
    return Notification.objects.filter(user=user, read_at__isnull=True).update(
        read_at=now or timezone.now()
    )
