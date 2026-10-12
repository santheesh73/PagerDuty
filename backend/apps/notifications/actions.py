"""Paging writes. Notification rows are the durable record of "this person must be paged".

They are created inside the caller's transaction (the same one that escalated or opened
the incident), so a page can't be lost between "decided to page" and "enqueued". Delivery
runs afterwards in a task; if the broker drops that message, `sweep_stuck_notifications`
re-drives every row still pending.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Service
from apps.core import dispatch
from apps.incidents.models import EventType, Incident, Status
from apps.incidents.timeline import record

from .channels import CHANNELS, ChannelError, PermanentChannelError, unavailable_reason
from .models import Notification, NotificationRule, UserContact

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
STUCK_AFTER = timedelta(seconds=90)
# A failed attempt is retried after 30 s, then 60, 120, 240: about seven and a half minutes in
# all, so an SMTP outage of a minute or two does not fail the page. (It used to be five attempts in
# about 17 seconds.) The Celery task, `redispatch_stuck` and `deliver_due` all honour this.
RETRY_BASE_SECONDS = 30


def retry_delay(attempts: int) -> timedelta:
    """How long to wait after the `attempts`-th failed attempt before the next one."""
    return timedelta(seconds=RETRY_BASE_SECONDS * 2 ** max(attempts - 1, 0))


# How long a worker may hold a notification while sending before another may take over.
# Must stay above EMAIL_TIMEOUT and below STUCK_AFTER, so a dead worker's page is retried by
# the next sweep.
CLAIM_TTL = timedelta(seconds=60)


def idempotency_key(
    incident_id: int, level: int, loop: int, user_id: int, channel: str, seq: int | None = None
) -> str:
    key = f"incident:{incident_id}:level:{level}:loop:{loop}:user:{user_id}:channel:{channel}"
    return f"{key}:seq:{seq}" if seq is not None else key


@dataclass(frozen=True)
class Step:
    """One thing to do for one person when they are paged: a channel, and how long to wait."""

    channel: str
    position: int | None  # the rule's position; None for the built-in defaults
    delay_minutes: int = 0

    @property
    def snapshot(self) -> dict:
        if self.position is None:
            return {}
        return {
            "v": 1,
            "position": self.position,
            "channel": self.channel,
            "delay_minutes": self.delay_minutes,
        }


def steps_for(user: User, incident: Incident) -> list[Step]:
    """The person's plan for this incident, read once at page time.

    The inbox entry is always created. With no enabled personal rules the default is email
    immediately; with rules, the rules that match the incident's urgency are the plan (so a
    person who only wants calls for high urgency gets exactly that).
    """
    steps = [Step(Notification.Channel.IN_APP, None)]
    rules = list(
        NotificationRule.objects.filter(user=user, enabled=True).order_by(
            "delay_minutes", "position"
        )
    )
    if not rules:
        steps.append(Step(Notification.Channel.EMAIL, None))
        return steps
    for rule in rules:
        if rule.urgency in (NotificationRule.Urgency.ANY, incident.urgency):
            steps.append(Step(rule.channel, rule.position, rule.delay_minutes))
    return steps


def page_key(incident_id: int, level: int, loop: int, user_id: int, seq: int | None) -> str:
    key = f"incident:{incident_id}:level:{level}:loop:{loop}:user:{user_id}"
    return f"{key}:seq:{seq}" if seq is not None else key


def page(
    incident: Incident,
    users: Iterable[User],
    *,
    level: int,
    loop: int,
    seq: int | None = None,
    now: datetime | None = None,
) -> list[Notification]:
    """Create (at most once per idempotency key) and dispatch notifications.

    Re-running with the same (incident, level, loop, seq) is a no-op: the unique key makes
    the second `get_or_create` find the first row instead of paging again, and `page_key`
    makes the person's rules apply exactly once even if they edit them in between.
    """
    if incident.is_maintenance:
        return []  # I13: maintenance incidents never page, whatever a human clicks
    now = now or timezone.now()
    dry_run = incident.service.mode == Service.Mode.DEBUG
    created: list[Notification] = []
    for user in users:
        key_prefix = page_key(incident.pk, level, loop, user.pk, seq)
        if Notification.objects.filter(incident=incident, page_key=key_prefix).exists():
            continue  # this page already happened; do not re-read the rules
        contact = UserContact.objects.filter(user=user).first()
        for step in steps_for(user, incident):
            notification, was_created = _create(
                incident, user, step, contact, level, loop, seq, key_prefix, now, dry_run
            )
            if was_created:
                created.append(notification)
    return created


def _destination(channel: str, user: User, contact: UserContact | None) -> str:
    if channel == Notification.Channel.EMAIL:
        return user.email
    if channel in (Notification.Channel.SMS, Notification.Channel.VOICE) and contact:
        return contact.phone_number
    if channel == Notification.Channel.WEBHOOK and contact and contact.webhook_url:
        return urlsplit(contact.webhook_url).hostname or ""  # the host only: URLs can be secrets
    return ""


def _create(
    incident: Incident,
    user: User,
    step: Step,
    contact: UserContact | None,
    level: int,
    loop: int,
    seq: int | None,
    key_prefix: str,
    now: datetime,
    dry_run: bool,
) -> tuple[Notification, bool]:
    key = idempotency_key(incident.pk, level, loop, user.pk, step.channel, seq)
    if step.position is not None:
        key += f":step:{step.position}"
    reason = None if dry_run else unavailable_reason(step.channel, contact)
    if dry_run:
        status = Notification.Status.DRY_RUN
    elif reason:
        status = Notification.Status.FAILED
    else:
        status = Notification.Status.PENDING
    delayed = step.delay_minutes > 0 and status == Notification.Status.PENDING
    not_before = now + timedelta(minutes=step.delay_minutes) if delayed else None
    notification, was_created = Notification.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "incident": incident,
            "user": user,
            "channel": step.channel,
            "status": status,
            "page_key": key_prefix,
            "not_before": not_before,
            "destination": _destination(step.channel, user, contact),
            "rule_snapshot": step.snapshot,
            "last_error": reason or "",
        },
    )
    if not was_created:
        return notification, False
    if dry_run:
        record(
            incident,
            EventType.NOTIFIED,
            user_id=user.pk,
            channel=step.channel,
            dry_run=True,
            message=f"Dry run: would notify {user} via {step.channel}",
        )
    elif reason:
        # Said out loud, now, rather than discovered after a delay: this page cannot reach them.
        record(
            incident,
            EventType.NOTIFICATION_FAILED,
            user_id=user.pk,
            channel=step.channel,
            attempts=0,
            message=f"Could not notify {user} via {step.channel}: {reason}",
        )
    else:
        from .tasks import deliver_notification

        dispatch.on_commit(deliver_notification, notification.pk, eta=not_before)
    return notification, True


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
        if notification.not_before is not None:
            if incident.status != Status.TRIGGERED:
                # I18: a later step of a personal plan exists to chase an *unanswered* page. Once
                # anyone acknowledges, it must not wake the person up.
                notification.status = Notification.Status.CANCELLED
                notification.save(update_fields=["status", "updated_at"])
                return notification, False
            if now < notification.not_before:
                return (
                    notification,
                    False,
                )  # I19: never before its time (an early or duplicate task)
        if notification.next_attempt_at is not None and now < notification.next_attempt_at:
            return notification, False  # a failed attempt is retried after its delay, not before
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
        if isinstance(error, PermanentChannelError):
            notification.last_error = str(error)[:2000]
            _fail(notification, notification.last_error)
            return notification
        if isinstance(error, ChannelError):
            notification.last_error = str(error)[:2000]
        else:
            # Not a declared transient failure: keep the type so the row says what broke.
            notification.last_error = f"{type(error).__name__}: {error}"[:2000]
        if notification.attempts >= MAX_ATTEMPTS:
            _fail(notification, notification.last_error)
            return notification
        notification.next_attempt_at = now + retry_delay(notification.attempts)
        notification.save(
            update_fields=["last_error", "claimed_at", "next_attempt_at", "updated_at"]
        )
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
            Q(not_before__isnull=True) | Q(not_before__lte=now),  # a future step is not stuck
            Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now),  # nor a waiting retry
            updated_at__lt=now - STUCK_AFTER,
            status=Notification.Status.PENDING,
            # `<=`: a worker that dies after its last claim leaves the row at the cap, and only
            # `deliver` (via `_claim`) can fail it, so the sweepers must hand it over too.
            attempts__lte=MAX_ATTEMPTS,
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


def deliver_due(*, now: datetime | None = None, limit: int = 100) -> int:
    """Send pending notifications that are due, in this process. Returns how many were sent.

    For demo mode, where there is no worker: a page whose inline send failed, or a later step of a
    personal plan whose time has come, is sent here by `/internal/tick/`. Each send goes through
    the same claim, so a concurrent tick or inline send can never page twice (I4).
    """
    now = now or timezone.now()
    ids = list(
        Notification.objects.filter(
            Q(not_before__isnull=True) | Q(not_before__lte=now),
            Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now),
            status=Notification.Status.PENDING,
            attempts__lte=MAX_ATTEMPTS,  # see redispatch_stuck
        )
        .order_by("pk")
        .values_list("pk", flat=True)[:limit]
    )
    sent = 0
    for pk in ids:
        try:
            result = deliver(pk, now=now)
        except ChannelError:
            continue  # the attempt is counted; the next tick tries again
        except Exception:
            logger.exception("tick delivery failed", extra={"notification_id": pk})
            continue
        sent += bool(result and result.status == Notification.Status.SENT)
    return sent


def mark_read(notification: Notification, *, now: datetime | None = None) -> Notification:
    if notification.read_at is None:
        notification.read_at = now or timezone.now()
        notification.save(update_fields=["read_at", "updated_at"])
    return notification


def mark_all_read(user: User, *, now: datetime | None = None) -> int:
    return Notification.objects.filter(user=user, read_at__isnull=True).update(
        read_at=now or timezone.now()
    )


# Carrier/provider states, ranked so a late or replayed callback can never move a row backwards.
_PROVIDER_RANK = {
    "accepted": 0, "queued": 0, "scheduled": 0,
    "sending": 1,
    "sent": 2, "ringing": 2,
    "in-progress": 3, "receiving": 3,
    "delivered": 4, "read": 4, "completed": 4,
    "failed": 5, "undelivered": 5, "busy": 5, "no-answer": 5, "canceled": 5,
}  # fmt: skip
_PROVIDER_FAILURES = {"failed", "undelivered", "busy", "no-answer", "canceled"}


def apply_provider_status(
    provider_id: str, state: str, *, now: datetime | None = None
) -> Notification | None:
    """Record a delivery receipt. Idempotent and monotonic: replays and out-of-order callbacks
    (Twilio does not guarantee order) change nothing."""
    rank = _PROVIDER_RANK.get(state)
    if rank is None:
        return None
    now = now or timezone.now()
    with transaction.atomic():
        notification = (
            Notification.objects.select_for_update(of=("self",))
            .select_related("incident", "user")
            .filter(provider_id=provider_id)
            .first()
        )
        if notification is None:
            return None  # a receipt for something we never sent (or already purged)
        current = _PROVIDER_RANK.get(notification.provider_status, -1)
        if rank <= current:
            return notification
        notification.provider_status = state
        fields = ["provider_status", "updated_at"]
        if state in ("delivered", "completed") and notification.delivered_at is None:
            notification.delivered_at = now
            fields.append("delivered_at")
        notification.save(update_fields=fields)
        if state in _PROVIDER_FAILURES:
            record(
                notification.incident,
                EventType.NOTIFICATION_FAILED,
                user_id=notification.user_id,
                channel=notification.channel,
                attempts=notification.attempts,
                message=(
                    f"The carrier reported {state} for {notification.user} via "
                    f"{notification.get_channel_display()}"
                ),
            )
        return notification
