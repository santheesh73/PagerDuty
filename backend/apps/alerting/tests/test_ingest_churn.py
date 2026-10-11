"""Sustained trigger/resolve churn on one dedup key must never drop an alert.

A trigger that loses the race to open an incident retries as an attach. With only two attempts, a
resolve landing between them sent the alert to HTTP 409 `ingest_conflict`: the alert was dropped
and the monitor had to notice and resend. Reproduced with 8 looping triggers against 8 looping
resolvers (6 dropped alerts on every run)."""

import threading

import pytest
from django.db import connections

from apps.alerting.actions import Event, IngestConflict, ingest
from apps.core.invariants import check_invariants
from apps.incidents.models import Incident, Status
from conftest import T0
from tests.factories import ServiceFactory

pytestmark = pytest.mark.django_db(transaction=True)

THREADS = 8
TRIGGERS_EACH = 25
RESOLVES_EACH = 60


def event(action: str) -> Event:
    return Event(action=action, dedup_key="hot", summary="churn", severity="critical", source="t")


def test_trigger_resolve_churn_on_one_key_drops_no_alert() -> None:
    service = ServiceFactory()
    gate = threading.Barrier(THREADS * 2)
    lock = threading.Lock()
    errors: list[BaseException] = []
    accepted: list[object] = []

    def run(fn) -> None:
        try:
            gate.wait()
            fn()
        except BaseException as exc:
            with lock:
                errors.append(exc)
        finally:
            connections.close_all()

    def trigger() -> None:
        for _ in range(TRIGGERS_EACH):
            result = ingest(service, event("trigger"), now=T0)
            with lock:
                accepted.append(result)

    def resolve() -> None:
        for _ in range(RESOLVES_EACH):
            ingest(service, event("resolve"), now=T0)

    threads = [threading.Thread(target=run, args=(trigger,)) for _ in range(THREADS)]
    threads += [threading.Thread(target=run, args=(resolve,)) for _ in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    conflicts = [e for e in errors if isinstance(e, IngestConflict)]
    others = [e for e in errors if not isinstance(e, IngestConflict)]
    assert not others, others[:3]
    assert not conflicts, f"{len(conflicts)} alerts dropped with ingest_conflict"
    assert len(accepted) == THREADS * TRIGGERS_EACH
    # The guarantee that already held and must keep holding.
    open_for_key = Incident.objects.filter(service=service, dedup_key="hot").exclude(
        status=Status.RESOLVED
    )
    assert open_for_key.count() <= 1
    assert not check_invariants()
