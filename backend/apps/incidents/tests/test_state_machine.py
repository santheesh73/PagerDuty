from datetime import timedelta

import pytest

from apps.core.errors import Conflict, InvalidTransition, LimitExceeded
from apps.core.limits import MAX_NOTE_LENGTH
from apps.incidents import actions
from apps.incidents.actions import TRANSITIONS, Action
from apps.incidents.models import EventType, Incident, Status
from apps.notifications.models import Notification
from conftest import T0, Paging
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

MIN = timedelta(minutes=1)


def put_in(incident: Incident, status: Status, people: Paging) -> Incident:
    if status in (Status.ACKNOWLEDGED, Status.RESOLVED):
        actions.acknowledge(incident.pk, actor=people.on_call, now=T0 + MIN)
    if status == Status.RESOLVED:
        actions.resolve(incident.pk, actor=people.on_call, now=T0 + 2 * MIN)
    incident.refresh_from_db()
    assert incident.status == status
    return incident


def run(action: Action, incident: Incident, people: Paging) -> None:
    now = T0 + 3 * MIN
    match action:
        case Action.ACKNOWLEDGE:
            actions.acknowledge(incident.pk, actor=people.on_call, now=now)
        case Action.UNACKNOWLEDGE:
            actions.unacknowledge(incident.pk, actor=people.on_call, now=now)
        case Action.RESOLVE:
            actions.resolve(incident.pk, actor=people.on_call, now=now)
        case Action.REASSIGN:
            actions.reassign(incident.pk, actor=people.on_call, assignee=people.off_call, now=now)
        case Action.ESCALATE:
            actions.escalate(incident.pk, actor=people.on_call, now=now)
        case Action.ADD_NOTE:
            actions.add_note(incident.pk, actor=people.on_call, text="Looking into it")


ALL_CASES = [(a, s) for a in Action for s in Status]


@pytest.mark.parametrize(("action", "status"), ALL_CASES, ids=lambda v: str(v))
def test_transition_table_is_enforced(
    open_incident: Incident, people: Paging, action: Action, status: Status
) -> None:
    incident = put_in(open_incident, status, people)
    sources, target = TRANSITIONS[action]

    if status not in sources:
        with pytest.raises(InvalidTransition):
            run(action, incident, people)
        return

    events_before = incident.events.exclude(type=EventType.NOTIFIED).count()
    run(action, incident, people)
    incident.refresh_from_db()
    assert incident.status == (target or status)
    # Exactly one timeline entry per action (delivery receipts are separate).
    assert incident.events.exclude(type=EventType.NOTIFIED).count() == events_before + 1


def test_resolved_is_terminal(open_incident: Incident, people: Paging) -> None:
    put_in(open_incident, Status.RESOLVED, people)
    for action in Action:
        with pytest.raises(InvalidTransition):
            run(action, open_incident, people)


def test_invalid_transition_explains_what_is_allowed(
    open_incident: Incident, people: Paging
) -> None:
    with pytest.raises(InvalidTransition) as exc:
        actions.unacknowledge(open_incident.pk, actor=people.on_call)
    assert exc.value.details["allowed"] == [
        "acknowledge",
        "resolve",
        "reassign",
        "escalate",
        "add_note",
    ]


def test_first_response_is_set_once_by_the_first_human_action(
    open_incident: Incident, people: Paging
) -> None:
    actions.add_note(open_incident.pk, actor=people.on_call, text="on it")
    open_incident.refresh_from_db()
    assert open_incident.first_response_at is None  # notes don't count

    actions.acknowledge(open_incident.pk, actor=people.on_call, now=T0 + 2 * MIN)
    actions.unacknowledge(open_incident.pk, actor=people.on_call, now=T0 + 4 * MIN)
    actions.resolve(open_incident.pk, actor=people.on_call, now=T0 + 6 * MIN)
    open_incident.refresh_from_db()
    assert open_incident.first_response_at == T0 + 2 * MIN


@pytest.mark.parametrize("action", sorted(actions.FIRST_RESPONSE_ACTIONS))
def test_every_human_action_counts_as_first_response(
    open_incident: Incident, people: Paging, action: Action
) -> None:
    if action == Action.UNACKNOWLEDGE:
        actions.acknowledge(open_incident.pk, actor=None, now=T0 + MIN, via="events_api")
    run(action, open_incident, people)
    open_incident.refresh_from_db()
    assert open_incident.first_response_at == T0 + 3 * MIN


def test_acknowledged_at_keeps_the_first_acknowledgement(
    open_incident: Incident, people: Paging
) -> None:
    actions.acknowledge(open_incident.pk, actor=people.on_call, now=T0 + MIN)
    actions.unacknowledge(open_incident.pk, actor=people.on_call, now=T0 + 2 * MIN)
    actions.acknowledge(open_incident.pk, actor=people.on_call, now=T0 + 3 * MIN)
    open_incident.refresh_from_db()
    assert open_incident.acknowledged_at == T0 + MIN


def test_acknowledge_assigns_the_actor_when_unassigned(
    open_incident: Incident, people: Paging
) -> None:
    Incident.objects.filter(pk=open_incident.pk).update(assignee=None)
    actions.acknowledge(open_incident.pk, actor=people.admin, now=T0 + MIN)
    open_incident.refresh_from_db()
    assert open_incident.assignee == people.admin


def test_resolve_resolves_attached_alerts_and_clears_the_timer(
    open_incident: Incident, people: Paging
) -> None:
    actions.resolve(open_incident.pk, actor=people.on_call, now=T0 + MIN)
    open_incident.refresh_from_db()
    assert open_incident.next_escalation_at is None
    assert open_incident.resolved_at == T0 + MIN
    assert set(open_incident.alerts.values_list("status", flat=True)) == {"resolved"}


def test_reassign_pages_the_new_assignee_and_restarts_the_timer(
    open_incident: Incident, people: Paging
) -> None:
    actions.acknowledge(open_incident.pk, actor=people.on_call, now=T0 + MIN)
    newcomer = UserFactory()
    actions.reassign(open_incident.pk, actor=people.on_call, assignee=newcomer, now=T0 + 3 * MIN)

    open_incident.refresh_from_db()
    assert open_incident.status == Status.TRIGGERED
    assert open_incident.assignee == newcomer
    assert open_incident.next_escalation_at == T0 + 8 * MIN
    assert Notification.objects.filter(incident=open_incident, user=newcomer).count() == 2


def test_manual_escalate_jumps_one_level_immediately(
    open_incident: Incident, people: Paging
) -> None:
    actions.escalate(open_incident.pk, actor=people.on_call, now=T0 + MIN)
    open_incident.refresh_from_db()
    assert open_incident.escalation_level == 1
    assert open_incident.assignee == people.admin
    assert open_incident.next_escalation_at == T0 + 11 * MIN
    event = open_incident.events.exclude(type=EventType.NOTIFIED).last()
    assert (event.type, event.actor) == (EventType.MANUAL_ESCALATED, people.on_call)


def test_manual_escalate_past_the_last_level_is_a_conflict(
    open_incident: Incident, people: Paging
) -> None:
    actions.escalate(open_incident.pk, actor=people.on_call, now=T0 + MIN)
    with pytest.raises(Conflict):
        actions.escalate(open_incident.pk, actor=people.on_call, now=T0 + 2 * MIN)


def test_note_length_is_limited(open_incident: Incident, people: Paging) -> None:
    actions.add_note(open_incident.pk, actor=people.on_call, text="x" * MAX_NOTE_LENGTH)
    with pytest.raises(LimitExceeded):
        actions.add_note(open_incident.pk, actor=people.on_call, text="x" * (MAX_NOTE_LENGTH + 1))
