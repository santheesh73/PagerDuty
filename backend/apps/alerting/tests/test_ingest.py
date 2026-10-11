import threading
from datetime import timedelta

import pytest
from django.db import connection

from apps.alerting.actions import Event, ingest
from apps.alerting.models import Alert
from apps.catalog import actions as catalog_actions
from apps.catalog.models import Service
from apps.core.errors import Conflict
from apps.incidents import actions
from apps.incidents.models import EventType, Incident, Status
from apps.notifications.models import Notification
from conftest import T0, Paging, TriggerFn
from tests.factories import ServiceFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("severity", "urgency"),
    [("critical", "high"), ("error", "high"), ("warning", "low"), ("info", "low")],
)
def test_severity_maps_to_urgency(
    service: Service, trigger: TriggerFn, severity: str, urgency: str
) -> None:
    result = trigger(service, severity=severity)
    assert Incident.objects.get(pk=result.incident_id).urgency == urgency


def test_trigger_returns_accepted_with_the_new_incident(
    service: Service, trigger: TriggerFn
) -> None:
    result = trigger(service, "db-down")
    assert (result.status, result.dedup_key, result.created) == ("accepted", "db-down", True)
    incident = Incident.objects.get(pk=result.incident_id)
    assert incident.title == "Disk 95% full on db-1"
    assert incident.alerts.count() == 1


def test_same_dedup_key_attaches_to_the_open_incident(service: Service, trigger: TriggerFn) -> None:
    first = trigger(service, "disk")
    second = trigger(service, "disk", now=T0 + timedelta(minutes=1))

    assert second.incident_id == first.incident_id
    assert second.created is False
    incident = Incident.objects.get(pk=first.incident_id)
    assert incident.alert_count == 2
    assert incident.alerts.count() == 2
    assert list(incident.events.values_list("type", flat=True)) == [
        EventType.TRIGGERED,
        EventType.ALERT_ATTACHED,
    ]


def test_duplicates_do_not_page_again(service: Service, trigger: TriggerFn) -> None:
    trigger(service, "disk")
    trigger(service, "disk")
    assert Notification.objects.count() == 2  # one page: in-app + email


def test_missing_dedup_key_generates_a_unique_one(service: Service, trigger: TriggerFn) -> None:
    a = trigger(service, None)
    b = trigger(service, None)
    assert a.dedup_key != b.dedup_key
    assert a.incident_id != b.incident_id


def test_dedup_is_scoped_to_the_service(trigger: TriggerFn) -> None:
    a = trigger(ServiceFactory(), "same-key")
    b = trigger(ServiceFactory(), "same-key")
    assert a.incident_id != b.incident_id


def test_trigger_after_resolve_opens_a_new_incident(
    service: Service, trigger: TriggerFn, people: Paging
) -> None:
    first = trigger(service, "disk")
    actions.resolve(first.incident_id, actor=people.on_call, now=T0 + timedelta(minutes=3))
    second = trigger(service, "disk", now=T0 + timedelta(minutes=4))

    assert second.created is True
    assert second.incident_id != first.incident_id


@pytest.mark.django_db(transaction=True)
def test_concurrent_triggers_with_one_key_create_exactly_one_incident(trigger: TriggerFn) -> None:
    service = ServiceFactory()
    workers = 8
    barrier = threading.Barrier(workers)
    errors: list[BaseException] = []

    def fire() -> None:
        try:
            barrier.wait()
            trigger(service, "thundering-herd")
        except BaseException as exc:  # surface thread failures in the main thread
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=fire) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    incident = Incident.objects.get(service=service)
    assert incident.alert_count == workers
    assert Alert.objects.filter(incident=incident).count() == workers
    assert incident.events.filter(type=EventType.TRIGGERED).count() == 1


def test_acknowledge_event_by_dedup_key(service: Service, trigger: TriggerFn) -> None:
    opened = trigger(service, "disk")
    result = trigger(service, "disk", action="acknowledge", now=T0 + timedelta(minutes=2))

    incident = Incident.objects.get(pk=opened.incident_id)
    assert result.status == "accepted"
    assert incident.status == Status.ACKNOWLEDGED
    assert incident.acknowledged_at == T0 + timedelta(minutes=2)
    assert incident.next_escalation_at is None
    # Source-driven: the monitoring system acknowledged, not a human.
    assert incident.first_response_at is None


def test_resolve_event_by_dedup_key(service: Service, trigger: TriggerFn) -> None:
    opened = trigger(service, "disk")
    trigger(service, "disk", action="resolve", now=T0 + timedelta(minutes=9))

    incident = Incident.objects.get(pk=opened.incident_id)
    assert incident.status == Status.RESOLVED
    assert incident.resolved_at == T0 + timedelta(minutes=9)
    assert incident.first_response_at is None
    assert set(incident.alerts.values_list("status", flat=True)) == {Alert.Status.RESOLVED}


def test_unknown_dedup_key_is_ignored(service: Service, trigger: TriggerFn) -> None:
    result = trigger(service, "never-seen", action="resolve")
    assert (result.status, result.incident_id) == ("ignored", None)


def test_repeated_acknowledge_event_is_ignored(service: Service, trigger: TriggerFn) -> None:
    trigger(service, "disk")
    trigger(service, "disk", action="acknowledge")
    assert trigger(service, "disk", action="acknowledge").status == "ignored"


def test_maintenance_consolidates_every_alert_into_one_quiet_incident(
    service: Service, trigger: TriggerFn
) -> None:
    catalog_actions.set_mode(
        service, Service.Mode.MAINTENANCE, until=T0 + timedelta(hours=1), now=T0
    )
    service.refresh_from_db()
    results = [trigger(service, key) for key in ("cpu", "disk", "cpu")]

    assert len({r.incident_id for r in results}) == 1
    incident = Incident.objects.get(pk=results[0].incident_id)
    assert incident.is_maintenance is True
    assert incident.urgency == "low"
    assert incident.alert_count == 3
    assert incident.next_escalation_at is None
    assert Notification.objects.count() == 0
    assert set(Alert.objects.values_list("status", flat=True)) == {Alert.Status.SUPPRESSED}
    assert incident.events.first().type == EventType.MAINTENANCE_STARTED


@pytest.mark.parametrize("action", ["unacknowledge", "reassign", "escalate"])
def test_human_actions_on_a_maintenance_incident_never_page(
    service: Service, trigger: TriggerFn, action: str
) -> None:
    """Found by the fault simulator (seed 20261011): I13 held only until someone clicked."""
    catalog_actions.set_mode(
        service, Service.Mode.MAINTENANCE, until=T0 + timedelta(hours=1), now=T0
    )
    service.refresh_from_db()
    incident_id = trigger(service, "cpu").incident_id
    paging = Paging(service)
    actor = paging.admin
    now = T0 + timedelta(minutes=1)
    if action == "unacknowledge":
        actions.acknowledge(incident_id, actor=actor, now=now)
        actions.unacknowledge(incident_id, actor=actor, now=now)
    elif action == "reassign":
        actions.reassign(incident_id, actor=actor, assignee=paging.on_call, now=now)
    else:
        with pytest.raises(Conflict):
            actions.escalate(incident_id, actor=actor, now=now)

    incident = Incident.objects.get(pk=incident_id)
    assert Notification.objects.count() == 0
    assert incident.next_escalation_at is None


def test_mode_expiry_returns_service_to_active_and_closes_maintenance(
    service: Service, trigger: TriggerFn
) -> None:
    catalog_actions.set_mode(
        service, Service.Mode.MAINTENANCE, until=T0 + timedelta(hours=1), now=T0
    )
    service.refresh_from_db()
    maintenance_id = trigger(service, "cpu").incident_id

    assert catalog_actions.expire_service_modes(now=T0 + timedelta(minutes=59)) == 0
    assert catalog_actions.expire_service_modes(now=T0 + timedelta(hours=1)) == 1

    service.refresh_from_db()
    assert (service.mode, service.mode_until) == (Service.Mode.ACTIVE, None)
    incident = Incident.objects.get(pk=maintenance_id)
    assert incident.status == Status.RESOLVED
    assert incident.events.last().type == EventType.MAINTENANCE_ENDED

    # Back in active mode, alerts page normally again.
    assert trigger(service, "cpu").created is True
    assert Notification.objects.count() == 2


def test_ingest_without_a_policy_target_still_records_the_incident() -> None:
    service = ServiceFactory(escalation_policy__rules=False)
    result = ingest(service, Event(action="trigger", dedup_key="x", summary="s"), now=T0)
    incident = Incident.objects.get(pk=result.incident_id)
    assert incident.next_escalation_at is None
    assert Notification.objects.count() == 0
