"""Escalation engine. Engines are called directly with an explicit `now`; Celery never runs
eagerly here, so these tests exercise the real timing model rather than a mocked one."""

import threading
from datetime import timedelta
from unittest import mock

import pytest
import time_machine
from django.core import mail
from django.db import connection

from apps.alerting.models import Alert
from apps.catalog.models import Service
from apps.escalations import engine
from apps.escalations.models import EscalationRule, EscalationTarget
from apps.escalations.tasks import sweep_due_escalations
from apps.incidents import actions
from apps.incidents.models import EventType, Incident, Status
from apps.notifications.actions import deliver
from apps.notifications.models import Notification
from apps.schedules.models import LayerMember
from conftest import T0, Paging, TriggerFn
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

MIN = timedelta(minutes=1)


def events(incident: Incident) -> list[str]:
    return list(incident.events.order_by("id").values_list("type", flat=True))


def paged(incident: Incident, **filters: object) -> list[int]:
    """User ids paged in-app for this incident (one row per page)."""
    return list(
        Notification.objects.filter(incident=incident, channel="in_app", **filters)
        .order_by("id")
        .values_list("user_id", flat=True)
    )


def test_trigger_pages_level_zero_and_starts_the_timer(
    open_incident: Incident, people: Paging
) -> None:
    assert open_incident.status == Status.TRIGGERED
    assert (open_incident.escalation_level, open_incident.escalation_loop) == (0, 0)
    assert open_incident.assignee == people.on_call
    assert open_incident.next_escalation_at == T0 + 5 * MIN
    assert paged(open_incident) == [people.on_call.pk]
    assert Notification.objects.filter(incident=open_incident).count() == 2  # in-app + email
    assert events(open_incident) == [EventType.TRIGGERED]


def test_escalates_to_the_next_level_when_due(open_incident: Incident, people: Paging) -> None:
    assert engine.escalate(open_incident.pk, 0, 0, T0 + 5 * MIN) is True

    open_incident.refresh_from_db()
    assert open_incident.escalation_level == 1
    assert open_incident.assignee == people.admin
    assert open_incident.next_escalation_at == T0 + 15 * MIN
    assert paged(open_incident) == [people.on_call.pk, people.admin.pk]
    assert events(open_incident)[-1] == EventType.ESCALATED


def test_does_not_escalate_before_the_delay_elapses(open_incident: Incident) -> None:
    assert engine.escalate(open_incident.pk, 0, 0, T0 + 5 * MIN - timedelta(seconds=1)) is False
    open_incident.refresh_from_db()
    assert open_incident.escalation_level == 0


def test_exhausts_after_the_last_level_when_no_loops_remain(open_incident: Incident) -> None:
    engine.escalate(open_incident.pk, 0, 0, T0 + 5 * MIN)
    assert engine.escalate(open_incident.pk, 1, 0, T0 + 15 * MIN) is True

    open_incident.refresh_from_db()
    assert open_incident.next_escalation_at is None
    assert events(open_incident)[-1] == EventType.ESCALATION_EXHAUSTED
    assert engine.escalate(open_incident.pk, 1, 0, T0 + 60 * MIN) is False


def test_loops_back_to_level_zero_when_loops_remain(
    service: Service, trigger: TriggerFn, people: Paging
) -> None:
    service.escalation_policy.num_loops = 1
    service.escalation_policy.save()
    incident = Incident.objects.get(pk=trigger(service).incident_id)

    engine.escalate(incident.pk, 0, 0, T0 + 5 * MIN)  # → L1, loop 0
    engine.escalate(incident.pk, 1, 0, T0 + 15 * MIN)  # → L0, loop 1
    incident.refresh_from_db()
    assert (incident.escalation_level, incident.escalation_loop) == (0, 1)
    # Same person, new loop → a new page with a distinct idempotency key.
    assert paged(incident) == [people.on_call.pk, people.admin.pk, people.on_call.pk]

    engine.escalate(incident.pk, 0, 1, T0 + 20 * MIN)  # → L1, loop 1
    engine.escalate(incident.pk, 1, 1, T0 + 30 * MIN)  # → exhausted
    incident.refresh_from_db()
    assert incident.next_escalation_at is None
    assert events(incident)[-1] == EventType.ESCALATION_EXHAUSTED


def test_ack_stops_escalation(open_incident: Incident, people: Paging) -> None:
    actions.acknowledge(open_incident.pk, actor=people.on_call, now=T0 + 2 * MIN)

    assert engine.escalate(open_incident.pk, 0, 0, T0 + 5 * MIN) is False
    assert engine.due_incidents(T0 + 60 * MIN) == []
    assert paged(open_incident) == [people.on_call.pk]


def test_eta_task_and_sweeper_double_fire_pages_once(
    open_incident: Incident, people: Paging
) -> None:
    due = T0 + 5 * MIN
    assert engine.escalate(open_incident.pk, 0, 0, due) is True  # the ETA task
    assert engine.escalate(open_incident.pk, 0, 0, due) is False  # the sweeper, same tick

    with time_machine.travel(due + timedelta(seconds=30), tick=False):
        assert sweep_due_escalations() == 0
    assert paged(open_incident) == [people.on_call.pk, people.admin.pk]
    assert events(open_incident).count(EventType.ESCALATED) == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_escalations_of_one_incident_page_once(
    service: Service, trigger: TriggerFn, people: Paging
) -> None:
    incident = Incident.objects.get(pk=trigger(service).incident_id)
    barrier = threading.Barrier(4)
    results: list[bool] = []

    def worker() -> None:
        try:
            barrier.wait()
            results.append(engine.escalate(incident.pk, 0, 0, T0 + 5 * MIN))
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == [False, False, False, True]
    assert paged(incident) == [people.on_call.pk, people.admin.pk]


def test_no_responder_moves_to_the_next_level_on_the_next_sweep(
    service: Service, trigger: TriggerFn, people: Paging
) -> None:
    LayerMember.objects.filter(layer__schedule=people.schedule).delete()
    incident = Incident.objects.get(pk=trigger(service).incident_id)

    assert incident.assignee is None
    assert incident.next_escalation_at == T0  # due immediately
    assert events(incident) == [EventType.TRIGGERED, EventType.NO_RESPONDER]

    with time_machine.travel(T0 + timedelta(seconds=30), tick=False):
        assert sweep_due_escalations() == 1
    incident.refresh_from_db()
    assert incident.escalation_level == 1
    assert incident.assignee == people.admin


def test_policy_edit_does_not_change_open_incident(open_incident: Incident, people: Paging) -> None:
    snapshot_before = dict(open_incident.escalation_snapshot)
    policy = open_incident.service.escalation_policy
    newcomer = UserFactory()
    l1 = EscalationRule.objects.get(policy=policy, level=1)
    EscalationTarget.objects.filter(rule=l1).update(target_user=newcomer)
    EscalationRule.objects.filter(policy=policy, level=0).update(delay_minutes=60)
    EscalationRule.objects.create(policy=policy, level=2, delay_minutes=1)

    assert engine.escalate(open_incident.pk, 0, 0, T0 + 5 * MIN) is True
    open_incident.refresh_from_db()
    assert open_incident.escalation_snapshot == snapshot_before
    assert open_incident.assignee == people.admin  # not the newcomer
    assert newcomer.pk not in paged(open_incident)


def test_schedule_targets_resolve_to_whoever_is_on_call_when_the_level_fires(
    service: Service, trigger: TriggerFn, people: Paging
) -> None:
    # The snapshot freezes structure, not people: after the 09:00 handoff, looping back
    # to level 0 pages the new on-call.
    service.escalation_policy.num_loops = 1
    service.escalation_policy.save()
    incident = Incident.objects.get(pk=trigger(service).incident_id)
    assert incident.assignee == people.on_call

    engine.escalate(incident.pk, 0, 0, T0 + 5 * MIN)
    after_handoff = T0 + timedelta(hours=21, minutes=30)  # Jan 8, 09:30 UTC
    engine.escalate(incident.pk, 1, 0, after_handoff)

    incident.refresh_from_db()
    assert (incident.escalation_level, incident.escalation_loop) == (0, 1)
    assert incident.assignee == people.off_call


def test_unacknowledge_restarts_the_timer_at_the_current_level(
    open_incident: Incident, people: Paging
) -> None:
    engine.escalate(open_incident.pk, 0, 0, T0 + 5 * MIN)  # L1: admin, 10 min
    actions.acknowledge(open_incident.pk, actor=people.admin, now=T0 + 6 * MIN)
    actions.unacknowledge(open_incident.pk, actor=people.admin, now=T0 + 8 * MIN)

    open_incident.refresh_from_db()
    assert open_incident.status == Status.TRIGGERED
    assert open_incident.next_escalation_at == T0 + 18 * MIN
    assert paged(open_incident) == [people.on_call.pk, people.admin.pk, people.admin.pk]
    assert engine.escalate(open_incident.pk, 1, 0, T0 + 17 * MIN) is False
    assert engine.escalate(open_incident.pk, 1, 0, T0 + 18 * MIN) is True


def test_low_urgency_never_escalates(service: Service, trigger: TriggerFn, people: Paging) -> None:
    incident = Incident.objects.get(pk=trigger(service, severity="warning").incident_id)

    assert incident.urgency == "low"
    assert incident.next_escalation_at is None
    assert paged(incident) == [people.on_call.pk]  # level 0 still hears about it
    assert engine.due_incidents(T0 + timedelta(days=1)) == []


def test_debug_mode_runs_the_pipeline_but_only_records_dry_runs(
    service: Service, trigger: TriggerFn, people: Paging
) -> None:
    service.mode = Service.Mode.DEBUG
    service.save()
    incident = Incident.objects.get(pk=trigger(service).incident_id)
    engine.escalate(incident.pk, 0, 0, T0 + 5 * MIN)

    rows = Notification.objects.filter(incident=incident)
    assert rows.count() == 4
    assert set(rows.values_list("status", flat=True)) == {Notification.Status.DRY_RUN}
    for row in rows:
        deliver(row.pk)
    assert mail.outbox == []
    assert incident.events.filter(type=EventType.NOTIFIED, data__dry_run=True).count() == 4


def test_sweeper_recovers_when_the_eta_message_is_lost(
    service: Service, trigger: TriggerFn, people: Paging, django_capture_on_commit_callbacks
) -> None:
    # Capture (and drop) every on-commit dispatch: the ETA task never reaches a worker.
    with django_capture_on_commit_callbacks(execute=False):
        incident = Incident.objects.get(pk=trigger(service).incident_id)

    with time_machine.travel(T0 + 5 * MIN, tick=False):
        assert sweep_due_escalations() == 1
    incident.refresh_from_db()
    assert incident.escalation_level == 1
    assert incident.assignee == people.admin


def test_broker_outage_does_not_fail_ingest(
    service: Service, trigger: TriggerFn, django_capture_on_commit_callbacks
) -> None:
    from apps.escalations.tasks import escalate_incident
    from apps.notifications.tasks import deliver_notification

    with (
        mock.patch.object(escalate_incident, "apply_async", side_effect=ConnectionError),
        mock.patch.object(deliver_notification, "apply_async", side_effect=ConnectionError),
        django_capture_on_commit_callbacks(execute=True),
    ):
        result = trigger(service)

    incident = Incident.objects.get(pk=result.incident_id)
    assert incident.next_escalation_at == T0 + 5 * MIN  # the DB still holds the timer
    assert Alert.objects.filter(incident=incident).count() == 1


def test_eta_task_is_dispatched_on_commit_for_the_due_time(
    service: Service, trigger: TriggerFn, django_capture_on_commit_callbacks
) -> None:
    from apps.escalations.tasks import escalate_incident

    with (
        mock.patch.object(escalate_incident, "apply_async") as apply_async,
        django_capture_on_commit_callbacks(execute=True),
    ):
        result = trigger(service)

    apply_async.assert_called_once_with(
        args=(result.incident_id, 0, 0), kwargs={}, eta=T0 + 5 * MIN
    )
