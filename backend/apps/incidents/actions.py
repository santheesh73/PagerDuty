"""Incident writes: opening incidents and the human/source state machine.

Every action:
* locks the incident row (`select_for_update`) so concurrent clicks serialise;
* checks the transition against `TRANSITIONS` — anything else is `InvalidTransition` (409);
* writes exactly one IncidentEvent (notification deliveries add their own `notified` rows);
* dispatches side effects via `transaction.on_commit`, never before the data is durable.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User
from apps.alerting.models import Alert
from apps.catalog.models import Service
from apps.core import limits
from apps.core.errors import Conflict, InvalidTransition
from apps.escalations import engine
from apps.escalations.snapshot import build_snapshot, next_step
from apps.notifications.actions import page
from apps.notifications.models import Notification

from .models import EventType, Incident, IncidentEvent, Status, Urgency
from .timeline import record


class Action(StrEnum):
    ACKNOWLEDGE = "acknowledge"
    UNACKNOWLEDGE = "unacknowledge"
    RESOLVE = "resolve"
    REASSIGN = "reassign"
    ESCALATE = "escalate"
    ADD_NOTE = "add_note"


OPEN = frozenset({Status.TRIGGERED, Status.ACKNOWLEDGED})

# action → (allowed source states, target state or None for "unchanged")
TRANSITIONS: dict[Action, tuple[frozenset[Status], Status | None]] = {
    Action.ACKNOWLEDGE: (frozenset({Status.TRIGGERED}), Status.ACKNOWLEDGED),
    Action.UNACKNOWLEDGE: (frozenset({Status.ACKNOWLEDGED}), Status.TRIGGERED),
    Action.RESOLVE: (OPEN, Status.RESOLVED),
    Action.REASSIGN: (OPEN, Status.TRIGGERED),
    Action.ESCALATE: (OPEN, Status.TRIGGERED),
    Action.ADD_NOTE: (OPEN, None),
}

# Human actions that count as the incident's first response (notes deliberately don't).
FIRST_RESPONSE_ACTIONS = frozenset(
    {Action.ACKNOWLEDGE, Action.UNACKNOWLEDGE, Action.RESOLVE, Action.REASSIGN, Action.ESCALATE}
)


def allowed_actions(status: str) -> list[str]:
    return [a.value for a, (sources, _) in TRANSITIONS.items() if status in sources]


def _lock(incident_id: int) -> Incident:
    return (
        Incident.objects.select_for_update(of=("self",))
        .select_related("service")
        .get(pk=incident_id)
    )


def _transition(incident: Incident, action: Action, actor: User | None, now: datetime) -> None:
    sources, target = TRANSITIONS[action]
    if incident.status not in sources:
        raise InvalidTransition(
            f"Cannot {action.value.replace('_', ' ')} an incident that is {incident.status}.",
            details={
                "action": action.value,
                "status": incident.status,
                "allowed": allowed_actions(incident.status),
            },
        )
    if target is not None:
        incident.status = target
    # Source-driven changes (Events API, actor=None) are not a human response.
    if (
        actor is not None
        and action in FIRST_RESPONSE_ACTIONS
        and incident.first_response_at is None
    ):
        incident.first_response_at = now


# --- open / attach ------------------------------------------------------------------------


def open_incident(
    service: Service,
    *,
    dedup_key: str,
    title: str,
    urgency: str,
    now: datetime,
    is_maintenance: bool = False,
) -> Incident:
    """Create an incident and page level 0. Must run inside the caller's transaction.

    Raises IntegrityError if another open incident already holds (service, dedup_key) —
    the ingest path catches that and retries as an attach.
    """
    incident = Incident(
        service=service,
        title=title[:1024],
        urgency=Urgency.LOW if is_maintenance else urgency,
        dedup_key=dedup_key,
        is_maintenance=is_maintenance,
        triggered_at=now,
        escalation_snapshot=build_snapshot(service.escalation_policy),
    )
    if is_maintenance:
        # Maintenance incidents collect alerts quietly: no responders, no timer, no pages.
        incident.save()
        record(
            incident,
            EventType.MAINTENANCE_STARTED,
            message=f"{service.name} is in maintenance; alerts are being collected quietly",
        )
        return incident

    responders = engine.apply_level(incident, 0, 0, now)
    incident.save()
    record(
        incident, EventType.TRIGGERED, level=0, to=[u.pk for u in responders], message=title[:200]
    )
    if not responders and engine.rule_at(incident, 0) is not None:
        record(
            incident,
            EventType.NO_RESPONDER,
            level=0,
            loop=0,
            message="Nobody on call at level 1; moving on",
        )
    page(incident, responders, level=0, loop=0, now=now)
    engine.schedule_eta(incident, now)
    return incident


# --- state machine ------------------------------------------------------------------------


def acknowledge(
    incident_id: int, *, actor: User | None, now: datetime | None = None, via: str = "web"
) -> Incident:
    now = now or timezone.now()
    with transaction.atomic():
        incident = _lock(incident_id)
        _transition(incident, Action.ACKNOWLEDGE, actor, now)
        incident.acknowledged_at = incident.acknowledged_at or now
        incident.next_escalation_at = None
        if incident.assignee_id is None and actor is not None:
            incident.assignee = actor
        incident.save()
        Alert.objects.filter(incident=incident, status=Alert.Status.TRIGGERED).update(
            status=Alert.Status.ACKNOWLEDGED
        )
        # The later steps of people's notification plans exist to chase an unanswered page.
        Notification.objects.filter(
            incident=incident, status=Notification.Status.PENDING, not_before__isnull=False
        ).update(status=Notification.Status.CANCELLED)
        record(
            incident,
            EventType.ACKNOWLEDGED,
            actor=actor,
            via=via,
            message="Acknowledged" if actor else f"Acknowledged by {via}",
        )
        return incident


def unacknowledge(incident_id: int, *, actor: User, now: datetime | None = None) -> Incident:
    """Back to triggered: the current level's timer restarts and its responders are re-paged."""
    now = now or timezone.now()
    with transaction.atomic():
        incident = _lock(incident_id)
        _transition(incident, Action.UNACKNOWLEDGE, actor, now)
        incident.next_escalation_at = engine.due_at(incident, now)
        incident.save()
        Alert.objects.filter(incident=incident, status=Alert.Status.ACKNOWLEDGED).update(
            status=Alert.Status.TRIGGERED
        )
        responders = (
            []
            if incident.is_maintenance
            else engine.responders_at(incident, incident.escalation_level, now)
        )
        event = record(
            incident,
            EventType.UNACKNOWLEDGED,
            actor=actor,
            to=[u.pk for u in responders],
            message="Unacknowledged; paging again",
        )
        # A fresh `seq` makes these new pages rather than duplicates of the original ones.
        page(
            incident,
            responders,
            level=incident.escalation_level,
            loop=incident.escalation_loop,
            seq=event.pk,
            now=now,
        )
        engine.schedule_eta(incident, now)
        return incident


def resolve(
    incident_id: int, *, actor: User | None, now: datetime | None = None, via: str = "web"
) -> Incident:
    now = now or timezone.now()
    with transaction.atomic():
        incident = _lock(incident_id)
        _transition(incident, Action.RESOLVE, actor, now)
        incident.resolved_at = now
        incident.next_escalation_at = None
        incident.save()
        Alert.objects.filter(incident=incident).filter(
            Q(status=Alert.Status.TRIGGERED) | Q(status=Alert.Status.ACKNOWLEDGED)
        ).update(status=Alert.Status.RESOLVED)
        event_type = EventType.MAINTENANCE_ENDED if incident.is_maintenance else EventType.RESOLVED
        record(
            incident,
            event_type,
            actor=actor,
            via=via,
            message="Resolved" if actor else f"Resolved by {via}",
        )
        return incident


def reassign(
    incident_id: int, *, actor: User, assignee: User, now: datetime | None = None
) -> Incident:
    now = now or timezone.now()
    with transaction.atomic():
        incident = _lock(incident_id)
        previous = incident.assignee_id
        _transition(incident, Action.REASSIGN, actor, now)
        incident.assignee = assignee
        incident.next_escalation_at = engine.due_at(incident, now)
        incident.save()
        event = record(
            incident,
            EventType.REASSIGNED,
            actor=actor,
            previous=previous,
            to=assignee.pk,
            message=f"Reassigned to {assignee}",
        )
        page(
            incident,
            [assignee],
            level=incident.escalation_level,
            loop=incident.escalation_loop,
            seq=event.pk,
            now=now,
        )
        engine.schedule_eta(incident, now)
        return incident


def escalate(incident_id: int, *, actor: User, now: datetime | None = None) -> Incident:
    """Jump one level now. Reuses the engine so manual and timed escalation can't diverge."""
    now = now or timezone.now()
    with transaction.atomic():
        incident = _lock(incident_id)
        if incident.is_maintenance:
            raise Conflict("Maintenance incidents don't escalate; they collect alerts quietly.")
        if (
            incident.status in OPEN
            and next_step(
                incident.escalation_snapshot, incident.escalation_level, incident.escalation_loop
            )
            is None
        ):
            raise Conflict(
                "There is no further escalation level to page.",
                details={"level": incident.escalation_level},
            )
        _transition(incident, Action.ESCALATE, actor, now)
        incident.next_escalation_at = now  # due now, so the engine's guard lets it through
        incident.save()
        engine.escalate(
            incident.pk, incident.escalation_level, incident.escalation_loop, now, actor=actor
        )
        incident.refresh_from_db()
        return incident


def add_note(incident_id: int, *, actor: User, text: str) -> IncidentEvent:
    limits.enforce("note_length", len(text))
    with transaction.atomic():
        incident = _lock(incident_id)
        _transition(incident, Action.ADD_NOTE, actor, timezone.now())
        incident.save(update_fields=["updated_at"])
        return record(incident, EventType.NOTE_ADDED, actor=actor, message=text)


def attach_alert(incident: Incident, alert: Alert) -> None:
    """Fold a duplicate alert into an open incident (caller holds the row lock)."""
    from django.db.models import F

    Incident.objects.filter(pk=incident.pk).update(alert_count=F("alert_count") + 1)
    incident.refresh_from_db(fields=["alert_count"])
    data: dict[str, Any] = {"alert_id": alert.pk, "alert_count": incident.alert_count}
    record(incident, EventType.ALERT_ATTACHED, message=alert.summary[:200], **data)
