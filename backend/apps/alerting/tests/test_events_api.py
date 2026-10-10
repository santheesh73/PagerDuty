import json

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.catalog.models import Service
from apps.core.limits import MAX_EVENT_PAYLOAD_BYTES
from apps.incidents.models import Incident

pytestmark = pytest.mark.django_db
URL = "/api/v1/events/"


def event(service: Service, action: str = "trigger", **extra: object) -> dict:
    body: dict = {
        "routing_key": service.integration_key,
        "event_action": action,
        "dedup_key": "db-1/disk",
    }
    if action == "trigger":
        body["payload"] = {"summary": "Disk full", "severity": "critical", "source": "prom"}
    body.update(extra)
    return body


@pytest.fixture(autouse=True)
def _clear_throttle_counters() -> None:
    cache.clear()


def test_trigger_is_accepted_without_session_or_csrf(service: Service) -> None:
    client = APIClient(enforce_csrf_checks=True)
    response = client.post(URL, event(service), format="json")

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["dedup_key"] == "db-1/disk"
    assert Incident.objects.filter(pk=body["incident_id"]).exists()


def test_unknown_routing_key_is_rejected_with_the_error_envelope(api_client: APIClient) -> None:
    response = api_client.post(
        URL,
        {
            "routing_key": "nope",
            "event_action": "trigger",
            "payload": {"summary": "x", "severity": "info", "source": "y"},
        },
        format="json",
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "invalid_routing_key"


def test_invalid_event_is_a_422_validation_error(api_client: APIClient, service: Service) -> None:
    response = api_client.post(URL, event(service, payload={"summary": "x"}), format="json")
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "payload" in error["details"]


def test_acknowledge_requires_a_dedup_key(api_client: APIClient, service: Service) -> None:
    response = api_client.post(URL, event(service, "acknowledge", dedup_key=""), format="json")
    assert response.status_code == 422


def test_oversized_payload_is_limit_exceeded(api_client: APIClient, service: Service) -> None:
    body = event(service)
    body["payload"]["custom_details"] = {"blob": "x" * MAX_EVENT_PAYLOAD_BYTES}
    response = api_client.post(URL, json.dumps(body), content_type="application/json")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "limit_exceeded"


def test_resolve_by_dedup_key_and_unknown_key_is_ignored(
    api_client: APIClient, service: Service
) -> None:
    api_client.post(URL, event(service), format="json")
    resolved = api_client.post(URL, event(service, "resolve"), format="json")
    ignored = api_client.post(URL, event(service, "resolve", dedup_key="other"), format="json")

    assert resolved.json()["status"] == "accepted"
    assert ignored.status_code == 202
    assert ignored.json() == {"status": "ignored", "dedup_key": "other", "incident_id": None}


def test_events_are_throttled_per_routing_key(
    api_client: APIClient, service: Service, settings
) -> None:
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {"events": "2/min", "login": "10/min"},
    }
    from apps.core.throttling import RoutingKeyThrottle

    RoutingKeyThrottle.THROTTLE_RATES = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    try:
        codes = [api_client.post(URL, event(service), format="json").status_code for _ in range(3)]
    finally:
        from rest_framework.settings import api_settings

        RoutingKeyThrottle.THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES
    assert codes == [202, 202, 429]


def test_throttle_fails_open_when_the_cache_is_down(
    api_client: APIClient, service: Service
) -> None:
    from unittest import mock

    with mock.patch("django.core.cache.cache.get", side_effect=ConnectionError("redis down")):
        response = api_client.post(URL, event(service), format="json")
    assert response.status_code == 202
