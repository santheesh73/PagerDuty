"""The incident row lock is what serialises concurrent actions. These tests widen the window
inside the critical section so that, without the lock, the race is certain rather than unlikely."""

import threading
import time
from unittest import mock

import pytest
from django.db import connections

from apps.alerting.actions import Event, ingest
from apps.core.errors import InvalidTransition
from apps.incidents import actions as incident_actions
from apps.incidents.models import EventType, Incident, Status
from conftest import T0, Paging

pytestmark = pytest.mark.django_db(transaction=True)


def test_two_concurrent_resolves_have_exactly_one_winner(service, people: Paging) -> None:
    incident = Incident.objects.get(
        pk=ingest(
            service,
            Event(action="trigger", dedup_key="k", summary="s", severity="critical"),
            now=T0,
        ).incident_id
    )
    real_record = incident_actions.record
    outcomes: list[str] = []
    lock = threading.Lock()
    gate = threading.Barrier(2)

    def slow_record(*args, **kwargs):
        time.sleep(0.4)  # hold the critical section open so the other thread arrives inside it
        return real_record(*args, **kwargs)

    def worker() -> None:
        try:
            gate.wait()
            incident_actions.resolve(incident.pk, actor=people.admin)
            result = "resolved"
        except InvalidTransition:
            result = "refused"
        finally:
            connections.close_all()
        with lock:
            outcomes.append(result)

    with mock.patch.object(incident_actions, "record", slow_record):
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert sorted(outcomes) == ["refused", "resolved"]
    assert incident.events.filter(type=EventType.RESOLVED).count() == 1


def test_a_resolve_waits_for_an_alert_that_is_being_attached(service, people: Paging) -> None:
    """An alert that arrives while its incident is being resolved must not be folded into a
    resolved incident: the two serialise on the incident row."""
    incident = Incident.objects.get(
        pk=ingest(
            service,
            Event(action="trigger", dedup_key="k", summary="s", severity="critical"),
            now=T0,
        ).incident_id
    )
    inside = threading.Event()
    order: list[str] = []
    lock = threading.Lock()
    real_attach = incident_actions.attach_alert

    def slow_attach(*args, **kwargs):
        inside.set()  # the trigger holds the incident row; let the resolver try now
        time.sleep(0.5)
        return real_attach(*args, **kwargs)

    def trigger() -> None:
        try:
            ingest(
                service,
                Event(action="trigger", dedup_key="k", summary="second", severity="critical"),
                now=T0,
            )
        finally:
            connections.close_all()
        with lock:
            order.append("trigger")

    def resolver() -> None:
        inside.wait(5)
        try:
            incident_actions.resolve(incident.pk, actor=people.admin)
        finally:
            connections.close_all()
        with lock:
            order.append("resolve")

    with mock.patch.object(incident_actions, "attach_alert", slow_attach):
        threads = [threading.Thread(target=trigger), threading.Thread(target=resolver)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert order == ["trigger", "resolve"], "the resolve overtook an in-flight attach"
    incident.refresh_from_db()
    assert incident.status == Status.RESOLVED
    assert incident.alert_count == 2
