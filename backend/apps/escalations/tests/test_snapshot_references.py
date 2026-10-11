"""An open incident's frozen policy still names schedules and users. Deleting one of them must be
refused while the incident is open, or the incident escalates through levels with nobody to page."""

import pytest
from django.db.models import ProtectedError
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.escalations.models import EscalationTarget
from apps.incidents import actions as incident_actions
from apps.incidents.models import Incident
from apps.schedules.models import Schedule
from conftest import Paging, TriggerFn

pytestmark = pytest.mark.django_db


def detach_from_live_policy(people: Paging) -> tuple[Schedule, User]:
    """Edit the live policy so only the open incident's snapshot still references them."""
    EscalationTarget.objects.get(target_schedule=people.schedule).delete()
    EscalationTarget.objects.get(target_user=people.admin).delete()
    return people.schedule, people.admin


def test_a_schedule_named_by_an_open_incident_cannot_be_deleted(
    api_client: APIClient, service, people: Paging, trigger: TriggerFn
) -> None:
    incident = Incident.objects.get(pk=trigger(service).incident_id)
    schedule, _ = detach_from_live_policy(people)

    api_client.force_login(people.admin)
    response = api_client.delete(f"/api/v1/schedules/{schedule.pk}/")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "in_use"
    assert Schedule.objects.filter(pk=schedule.pk).exists()
    incident.refresh_from_db()
    assert incident.status != "resolved"


def test_a_user_named_by_an_open_incident_cannot_be_deleted(
    service, people: Paging, trigger: TriggerFn
) -> None:
    trigger(service)
    _, admin = detach_from_live_policy(people)
    with pytest.raises(ProtectedError):
        admin.delete()
    assert User.objects.filter(pk=admin.pk).exists()


def test_once_the_incident_is_resolved_the_schedule_can_go(
    api_client: APIClient, service, people: Paging, trigger: TriggerFn
) -> None:
    incident = Incident.objects.get(pk=trigger(service).incident_id)
    schedule, _ = detach_from_live_policy(people)
    incident_actions.resolve(incident.pk, actor=people.admin)

    api_client.force_login(people.admin)
    assert api_client.delete(f"/api/v1/schedules/{schedule.pk}/").status_code == 204


def test_an_unreferenced_schedule_deletes_normally(api_client: APIClient, people: Paging) -> None:
    detach_from_live_policy(people)  # no incident is open
    api_client.force_login(people.admin)
    assert api_client.delete(f"/api/v1/schedules/{people.schedule.pk}/").status_code == 204


def test_removing_a_whole_team_still_works_because_its_incidents_go_with_it(
    service, people: Paging, trigger: TriggerFn
) -> None:
    """`seed_demo --reset` and a real team deletion cascade over schedules *and* incidents."""
    trigger(service)
    service.team.delete()
    assert not Incident.objects.exists()
    assert not Schedule.objects.exists()
