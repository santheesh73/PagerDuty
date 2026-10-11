"""A deactivated user must never be paged, whether they are a direct target or on call."""

from datetime import timedelta

import pytest

from apps.escalations import engine
from apps.incidents.models import EventType, Incident
from apps.notifications.models import Notification
from conftest import T0, Paging, TriggerFn

pytestmark = pytest.mark.django_db


def test_an_inactive_on_call_user_is_not_paged(service, people: Paging, trigger: TriggerFn) -> None:
    people.on_call.is_active = False
    people.on_call.save(update_fields=["is_active"])

    incident = Incident.objects.get(pk=trigger(service).incident_id)

    assert not Notification.objects.filter(incident=incident, user=people.on_call).exists()
    assert incident.events.filter(type=EventType.NO_RESPONDER).exists()


def test_an_inactive_direct_target_is_skipped_when_its_level_fires(
    service, people: Paging, trigger: TriggerFn
) -> None:
    incident = Incident.objects.get(pk=trigger(service).incident_id)
    people.admin.is_active = False
    people.admin.save(update_fields=["is_active"])

    assert engine.escalate(incident.pk, 0, 0, T0 + timedelta(minutes=5)) is True

    assert not Notification.objects.filter(incident=incident, user=people.admin).exists()


def test_resolve_targets_drops_inactive_users_and_keeps_order(people: Paging) -> None:
    people.off_call.is_active = False
    people.off_call.save(update_fields=["is_active"])
    targets = [
        {"type": "user", "id": people.off_call.pk},
        {"type": "user", "id": people.admin.pk},
        {"type": "user", "id": people.admin.pk},  # duplicate
        {"type": "user", "id": people.on_call.pk},
    ]
    users = engine.resolve_targets(targets, T0)
    assert [u.pk for u in users] == [people.admin.pk, people.on_call.pk]
