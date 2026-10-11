"""The escalation engine.

The database is the timer. `Incident.next_escalation_at` says when the incident should move
up a level, and two independent callers ask for that move:

* an ETA task enqueued on commit — low latency in the happy path;
* `sweep_due_escalations` every 30 s — the safety net when Redis lost the ETA message,
  a worker died, or the broker was down when we tried to enqueue.

Both call `escalate(incident_id, level, loop, now)`. The guarded query below only matches
an incident that is *still* triggered, *still* at that exact level/loop and *already* due.
Whichever caller gets there first moves it; the other matches nothing and returns. Combined
with idempotency keys on Notification rows, a double fire can never double-page.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from django.db import transaction

from apps.accounts.models import User
from apps.core import dispatch
from apps.incidents.models import EventType, Incident, Status, Urgency
from apps.incidents.timeline import record
from apps.notifications.actions import page
from apps.schedules.selectors import on_call_user_ids

from .snapshot import next_step

logger = logging.getLogger(__name__)


def resolve_targets(targets: list[dict[str, Any]], now: datetime) -> list[User]:
    """Snapshot targets → active users, in policy order, without duplicates."""
    schedule_ids = [t["id"] for t in targets if t["type"] == "schedule"]
    on_call = on_call_user_ids(schedule_ids, now) if schedule_ids else {}
    ordered: list[int] = []
    for target in targets:
        user_id = target["id"] if target["type"] == "user" else on_call.get(target["id"])
        if user_id is not None and user_id not in ordered:
            ordered.append(user_id)
    users = User.objects.filter(is_active=True).in_bulk(ordered)
    return [users[pk] for pk in ordered if pk in users]


def rule_at(incident: Incident, level: int) -> dict[str, Any] | None:
    rules = incident.escalation_snapshot.get("rules") or []
    return rules[level] if 0 <= level < len(rules) else None


def responders_at(incident: Incident, level: int, now: datetime) -> list[User]:
    rule = rule_at(incident, level)
    return resolve_targets(rule["targets"], now) if rule else []


def due_at(incident: Incident, now: datetime) -> datetime | None:
    """When the current level should escalate. Low urgency never escalates on its own."""
    rule = rule_at(incident, incident.escalation_level)
    if incident.urgency != Urgency.HIGH or rule is None:
        return None
    return now + timedelta(minutes=rule["delay_minutes"])


def apply_level(incident: Incident, level: int, loop: int, now: datetime) -> list[User]:
    """Move `incident` (in memory) to level/loop and work out who to page. Caller saves.

    With nobody on call at this level, a high-urgency incident is due again immediately so
    the next sweep moves past the empty level instead of waiting out its delay.
    """
    incident.escalation_level, incident.escalation_loop = level, loop
    responders = responders_at(incident, level, now)
    if responders:
        incident.assignee = responders[0]
        incident.next_escalation_at = due_at(incident, now)
    elif rule_at(incident, level) is None:
        incident.next_escalation_at = None  # empty policy: nothing to escalate to, ever
    else:
        incident.next_escalation_at = now if incident.urgency == Urgency.HIGH else None
    return responders


def schedule_eta(incident: Incident, now: datetime) -> None:
    """Enqueue the low-latency ETA escalation after commit (the sweeper backs it up)."""
    if incident.next_escalation_at and incident.next_escalation_at > now:
        from .tasks import escalate_incident

        dispatch.on_commit(
            escalate_incident,
            incident.pk,
            incident.escalation_level,
            incident.escalation_loop,
            eta=incident.next_escalation_at,
        )


def escalate(
    incident_id: int, level: int, loop: int, now: datetime, *, actor: User | None = None
) -> bool:
    """Advance one level if, and only if, the incident is still due at (level, loop).

    Returns True when this call moved the incident. `actor` marks a manual escalation, which
    the incident action has already made due (`next_escalation_at = now`) in this transaction.
    """
    with transaction.atomic():
        incident = (
            Incident.objects.select_for_update(skip_locked=True, of=("self",))
            .select_related("service")
            .filter(
                pk=incident_id,
                status=Status.TRIGGERED,
                escalation_level=level,
                escalation_loop=loop,
                next_escalation_at__lte=now,
            )
            .first()
        )
        if incident is None:
            return False  # acked, resolved, already escalated, or another worker holds it

        # Always the frozen snapshot, never the live policy.
        step = next_step(incident.escalation_snapshot, level, loop)
        if step is None:
            incident.next_escalation_at = None
            incident.save(update_fields=["next_escalation_at", "updated_at"])
            record(
                incident,
                EventType.ESCALATION_EXHAUSTED,
                actor=actor,
                level=level,
                loop=loop,
                message="Escalation policy exhausted; nobody further to page",
            )
            return True

        new_level, new_loop = step
        responders = apply_level(incident, new_level, new_loop, now)
        incident.save()
        to = [u.pk for u in responders]
        if actor is not None:
            record(
                incident,
                EventType.MANUAL_ESCALATED,
                actor=actor,
                level=new_level,
                loop=new_loop,
                to=to,
                message=f"Escalated to level {new_level + 1}",
            )
        elif responders:
            record(
                incident,
                EventType.ESCALATED,
                level=new_level,
                loop=new_loop,
                to=to,
                message=f"Escalated to level {new_level + 1}",
            )
        else:
            record(
                incident,
                EventType.NO_RESPONDER,
                level=new_level,
                loop=new_loop,
                message=f"Nobody on call at level {new_level + 1}; moving on",
            )
        page(incident, responders, level=new_level, loop=new_loop, now=now)
        schedule_eta(incident, now)
        logger.info(
            "incident escalated",
            extra={
                "incident_id": incident.pk,
                "escalation_level": new_level,
                "escalation_loop": new_loop,
            },
        )
        return True


def due_incidents(now: datetime, limit: int = 500) -> list[tuple[int, int, int]]:
    """(id, level, loop) for every triggered incident whose timer has expired.

    A plain read is enough here: `escalate` re-checks every condition under a row lock with
    SKIP LOCKED, so concurrent sweepers and ETA tasks can't both act on one incident.
    """
    return list(
        Incident.objects.filter(status=Status.TRIGGERED, next_escalation_at__lte=now)
        .order_by("next_escalation_at")
        .values_list("pk", "escalation_level", "escalation_loop")[:limit]
    )
