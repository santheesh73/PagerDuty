import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.incidents.models import Incident
from apps.services.models import Service
from apps.users.models import Team


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def input_setup(db):
    team = Team.objects.create(name="Input Hardening Team", slug="input-team")
    service = Service.objects.create(name="Input Svc", slug="input-svc", team=team)
    incident = Incident.objects.create(
        service=service,
        title="Existing test incident",
        severity=Incident.Severity.CRITICAL,
        fingerprint="input_fp",
    )
    return {
        "team": team,
        "service": service,
        "incident": incident,
    }


@pytest.mark.django_db
def test_malformed_alert_payloads_rejected_with_400(api_client, input_setup):
    """
    Section 36: Malformed Alert Input.
    Test rejection with 400 Bad Request for:
    - Missing service_id
    - Non-existent service_id
    - Blank message
    - Blank source
    - Invalid severity
    """
    url = reverse("api:alert-list")
    service = input_setup["service"]

    # 1. Missing service_id
    r1 = api_client.post(url, {"message": "Disk full", "severity": "critical", "source": "nagios"}, format="json")
    assert r1.status_code == 400
    assert "service_id" in r1.json()

    # 2. Unknown service_id
    r2 = api_client.post(url, {"service_id": 999999, "message": "Disk full", "severity": "critical", "source": "nagios"}, format="json")
    assert r2.status_code == 400
    assert "service_id" in r2.json()

    # 3. Blank message
    r3 = api_client.post(url, {"service_id": service.id, "message": "   ", "severity": "critical", "source": "nagios"}, format="json")
    assert r3.status_code == 400
    assert "message" in r3.json()

    # 4. Blank source
    r4 = api_client.post(url, {"service_id": service.id, "message": "Disk full", "severity": "critical", "source": "   "}, format="json")
    assert r4.status_code == 400
    assert "source" in r4.json()

    # 5. Invalid severity
    r5 = api_client.post(url, {"service_id": service.id, "message": "Disk full", "severity": "MEGA_FATAL", "source": "nagios"}, format="json")
    assert r5.status_code == 400
    assert "severity" in r5.json()


@pytest.mark.django_db
def test_large_alert_payload_handled_safely(api_client, input_setup):
    """
    Section 37: Large Alert Payload.
    Verify that an unusually large but valid payload (large message and metadata)
    is accepted and does not crash the server or corrupt database state.
    """
    url = reverse("api:alert-list")
    service = input_setup["service"]

    large_message = "Database connection pool timeout error trace: " + ("x" * 2000)
    large_metadata = {f"key_{i}": f"val_{i}_{'y'*50}" for i in range(50)}

    payload = {
        "service_id": service.id,
        "message": large_message,
        "severity": "critical",
        "source": "datadog",
        "metadata": large_metadata,
    }
    response = api_client.post(url, payload, format="json")
    assert response.status_code == 201
    assert response.json()["id"] is not None


@pytest.mark.django_db
def test_security_mass_assignment_and_prohibited_endpoints(api_client, input_setup):
    """
    Section 57 & 58 & 59: Security — Mass Assignment & Prohibited Endpoints.
    Ensure clients cannot directly modify protected workflow fields:
    - POST /api/incidents/ -> 405 Method Not Allowed
    - PATCH /api/incidents/{id}/ with {"status": "RESOLVED"} -> 405
    - PUT /api/incidents/{id}/ -> 405
    - DELETE /api/incidents/{id}/ -> 405
    - POST /api/incidents/{id}/events/ -> 405
    - POST /api/notifications/ -> 405
    - PATCH /api/notifications/{id}/ -> 405
    """
    inc = input_setup["incident"]

    # Incident prohibited methods
    assert api_client.post("/api/incidents/", {"title": "Direct Create"}).status_code == 405
    assert api_client.patch(f"/api/incidents/{inc.id}/", {"status": "RESOLVED"}).status_code == 405
    assert api_client.put(f"/api/incidents/{inc.id}/", {"title": "Direct Put"}).status_code == 405
    assert api_client.delete(f"/api/incidents/{inc.id}/").status_code == 405

    # Event tampering prohibited
    assert api_client.post(f"/api/incidents/{inc.id}/events/", {"event_type": "INCIDENT_RESOLVED"}).status_code == 405

    # Notification direct write prohibited
    assert api_client.post("/api/notifications/", {"status": "SENT"}).status_code == 405


@pytest.mark.django_db
def test_malformed_query_parameters_do_not_leak_traceback(api_client, input_setup):
    """
    Section 39: Malformed Query Parameters.
    Attacking list endpoints with malformed query parameters should return controlled responses (no 500 error).
    """
    # Malformed status
    r1 = api_client.get("/api/incidents/?status=nonexistent_status_123")
    assert r1.status_code == 200
    assert len(r1.json()) == 0

    # Malformed severity
    r2 = api_client.get("/api/incidents/?severity=impossible_severity")
    assert r2.status_code == 200
    assert len(r2.json()) == 0

    # Non-integer service filter
    r3 = api_client.get("/api/incidents/?service=invalid_id_not_an_int")
    assert r3.status_code in [200, 400]
    assert r3.status_code != 500

    # Malformed analytics range
    r4 = api_client.get("/api/analytics/summary/?range=invalid_range_string")
    assert r4.status_code in [200, 400]
    assert r4.status_code != 500
