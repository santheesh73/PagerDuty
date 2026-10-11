from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import Service
from apps.incidents.models import Incident
from conftest import Paging
from tests.factories import EscalationPolicyFactory

pytestmark = pytest.mark.django_db


def test_the_key_is_never_readable_after_it_was_issued(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    api_client.force_login(people.admin)
    body = api_client.get(f"/api/v1/services/{service.pk}/").json()
    assert body["integration_key"] is None, "only a hash is stored; there is nothing to return"
    assert body["integration_key_prefix"] == service.integration_key[:8]
    api_client.force_login(people.on_call)
    body = api_client.get(f"/api/v1/services/{service.pk}/").json()
    assert body["integration_key"] is None
    assert body["integration_key_prefix"] is None


def test_only_a_hash_of_the_key_is_stored(service: Service) -> None:
    from django.db import connection

    key = service.integration_key
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM catalog_service WHERE id = %s", [service.pk])
        row = cursor.fetchone()
    assert key not in [str(value) for value in row]


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
    assert len(rotated["integration_key"]) == 64
    assert rotated["integration_key"] != service.integration_key
    assert rotated["previous_key_expires_at"] is not None


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


# --- rotation grace window ------------------------------------------------------------------------


def _send(key: str) -> int:
    return (
        APIClient()
        .post(
            "/api/v1/events/",
            {
                "routing_key": key,
                "event_action": "trigger",
                "payload": {"summary": "x", "severity": "critical", "source": "t"},
            },
            format="json",
        )
        .status_code
    )


def test_after_rotation_both_keys_work_until_the_grace_window_ends(
    service: Service, settings
) -> None:
    from datetime import timedelta

    import time_machine
    from django.core.cache import cache
    from django.utils import timezone

    from apps.catalog.actions import rotate_integration_key

    cache.clear()
    old = service.integration_key
    assert old is not None
    new = rotate_integration_key(service)
    assert _send(old) == 202, "senders must not lose alerts while their config is updated"
    assert _send(new) == 202
    later = timezone.now() + timedelta(hours=settings.INTEGRATION_KEY_GRACE_HOURS, minutes=1)
    with time_machine.travel(later, tick=False):
        cache.clear()
        assert _send(old) == 403
        assert _send(new) == 202


def test_rotating_twice_retires_the_oldest_key_at_once(service: Service) -> None:
    from django.core.cache import cache

    from apps.catalog.actions import rotate_integration_key

    cache.clear()
    first = service.integration_key
    assert first is not None
    second = rotate_integration_key(service)
    third = rotate_integration_key(service)
    assert _send(first) == 403
    assert _send(second) == 202
    assert _send(third) == 202


def test_a_leaked_key_can_be_killed_immediately_with_no_grace(service: Service) -> None:
    from datetime import timedelta

    from django.core.cache import cache

    cache.clear()
    old = service.integration_key
    assert old is not None
    service.issue_key(grace=timedelta(0))
    service.save()
    assert _send(old) == 403
