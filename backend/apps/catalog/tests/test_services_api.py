from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import Service
from apps.incidents.models import Incident
from conftest import Paging
from tests.factories import EscalationPolicyFactory

pytestmark = pytest.mark.django_db


def test_only_admins_see_the_integration_key(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    api_client.force_login(people.admin)
    assert api_client.get(f"/api/v1/services/{service.pk}/").json()["integration_key"] == (
        service.integration_key
    )
    api_client.force_login(people.on_call)
    assert api_client.get(f"/api/v1/services/{service.pk}/").json()["integration_key"] is None


def test_list_includes_open_incident_counts(
    api_client: APIClient, service: Service, people: Paging, open_incident: Incident
) -> None:
    api_client.force_login(people.viewer)
    row = api_client.get("/api/v1/services/").json()["results"][0]
    assert row["open_incidents"] == {"high": 1, "low": 0}


def test_admin_creates_a_service_responder_cannot(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    body = {
        "team": service.team_id,
        "name": "search-api",
        "escalation_policy": service.escalation_policy_id,
    }
    api_client.force_login(people.on_call)
    assert api_client.post("/api/v1/services/", body, format="json").status_code == 403
    api_client.force_login(people.admin)
    created = api_client.post("/api/v1/services/", body, format="json")
    assert created.status_code == 201
    assert len(created.json()["integration_key"]) == 64


def test_policy_must_belong_to_the_same_team(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    api_client.force_login(people.admin)
    response = api_client.post(
        "/api/v1/services/",
        {
            "team": service.team_id,
            "name": "x",
            "escalation_policy": EscalationPolicyFactory(rules=False).pk,
        },
        format="json",
    )
    assert response.status_code == 422


def test_rotate_key_is_admin_only(api_client: APIClient, service: Service, people: Paging) -> None:
    api_client.force_login(people.on_call)
    assert api_client.post(f"/api/v1/services/{service.pk}/rotate-key/").status_code == 403
    api_client.force_login(people.admin)
    rotated = api_client.post(f"/api/v1/services/{service.pk}/rotate-key/").json()
    assert rotated["integration_key"] != service.integration_key


def test_responders_can_send_a_test_alert_viewers_cannot(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    api_client.force_login(people.viewer)
    assert api_client.post(f"/api/v1/services/{service.pk}/test-alert/").status_code == 403
    api_client.force_login(people.on_call)
    response = api_client.post(f"/api/v1/services/{service.pk}/test-alert/")
    assert response.status_code == 202
    incident = Incident.objects.get(pk=response.json()["incident_id"])
    assert incident.title.startswith("Test alert for")


def test_mode_switch_with_expiry(api_client: APIClient, service: Service, people: Paging) -> None:
    api_client.force_login(people.admin)
    until = timezone.now() + timedelta(hours=2)
    body = api_client.post(
        f"/api/v1/services/{service.pk}/mode/",
        {"mode": "maintenance", "until": until.isoformat()},
        format="json",
    ).json()
    assert body["mode"] == "maintenance"
    assert body["mode_until"] is not None

    past = api_client.post(
        f"/api/v1/services/{service.pk}/mode/",
        {"mode": "debug", "until": "2020-01-01T00:00:00Z"},
        format="json",
    )
    assert past.status_code == 422
    active = api_client.post(
        f"/api/v1/services/{service.pk}/mode/", {"mode": "active"}, format="json"
    ).json()
    assert (active["mode"], active["mode_until"]) == ("active", None)


def test_deleting_a_policy_in_use_is_a_conflict(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    api_client.force_login(people.admin)
    response = api_client.delete(f"/api/v1/escalation-policies/{service.escalation_policy_id}/")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "in_use"
    assert Service.objects.filter(pk=service.pk).exists()
