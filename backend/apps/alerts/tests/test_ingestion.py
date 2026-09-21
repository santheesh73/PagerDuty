import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.alerts.models import Alert
from apps.services.models import Service
from apps.users.models import Team


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def service():
    team = Team.objects.create(name="Backend Team", slug="backend", is_active=True)
    return Service.objects.create(name="Payment API", slug="payment-api", team=team, is_active=True)


@pytest.mark.django_db
def test_valid_alert_ingestion(client, service):
    """Verify successful alert ingestion via POST /api/alerts/."""
    url = reverse("api:alert-list")
    payload = {
        "service_id": service.id,
        "severity": "critical",
        "message": "HTTP 500 rate above 20%",
        "source": "prometheus",
        "metadata": {"cluster": "us-east-1"},
    }
    response = client.post(url, payload, format="json")
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["service"]["name"] == "Payment API"
    assert data["severity"] == "CRITICAL"
    assert data["source"] == "prometheus"
    assert data["message"] == "HTTP 500 rate above 20%"
    assert len(data["fingerprint"]) == 64
    assert data["received_at"] is not None
    assert data["metadata"]["cluster"] == "us-east-1"


@pytest.mark.django_db
def test_duplicate_alert_ingestion_generates_matching_fingerprint(client, service):
    """
    Verify that identical alerts sent twice are both persisted (Phase 2)
    and produce the exact same fingerprint (in preparation for Phase 3).
    """
    url = reverse("api:alert-list")
    payload = {
        "service_id": service.id,
        "severity": "high",
        "message": "Database replica lag > 60s",
        "source": "datadog",
    }

    resp1 = client.post(url, payload, format="json")
    assert resp1.status_code == 201
    alert1 = resp1.json()

    resp2 = client.post(url, payload, format="json")
    assert resp2.status_code == 201
    alert2 = resp2.json()

    assert alert1["id"] != alert2["id"]
    assert alert1["fingerprint"] == alert2["fingerprint"]
    assert Alert.objects.count() == 2


@pytest.mark.django_db
def test_list_and_filter_alerts(client, service):
    """Verify GET /api/alerts/ with filtering by service, severity, source."""
    other_team = Team.objects.create(name="Platform Team", slug="platform")
    other_srv = Service.objects.create(name="Auth API", slug="auth-api", team=other_team)

    url = reverse("api:alert-list")
    client.post(url, {"service_id": service.id, "severity": "CRITICAL", "message": "M1", "source": "prometheus"}, format="json")
    client.post(url, {"service_id": service.id, "severity": "LOW", "message": "M2", "source": "datadog"}, format="json")
    client.post(url, {"service_id": other_srv.id, "severity": "CRITICAL", "message": "M3", "source": "prometheus"}, format="json")

    # Filter by service
    r_srv = client.get(url, {"service": service.id})
    assert r_srv.status_code == 200
    assert len(r_srv.json()) == 2

    # Filter by severity
    r_sev = client.get(url, {"severity": "CRITICAL"})
    assert r_sev.status_code == 200
    assert len(r_sev.json()) == 2

    # Filter by source
    r_src = client.get(url, {"source": "datadog"})
    assert r_src.status_code == 200
    assert len(r_src.json()) == 1


@pytest.mark.django_db
def test_phase_2_acceptance_scenario(client):
    """
    Phase 2 Acceptance Scenario (Section 39):
    1. Team: Backend Team
    2. Create Service: POST /api/services/ -> Payment API (status="healthy")
    3. POST /api/alerts/ -> Payment API, severity="critical", message="HTTP 500 rate above 20%", source="prometheus"
    4. Expected: 201 Created with fingerprint and received_at
    5. POST identical Alert again -> another row created, same fingerprint
    6. POST alert with nonexistent service -> clean 400 validation error
    7. POST invalid severity -> clean 400 validation error
    """
    # 1. Team
    backend_team = Team.objects.create(name="Backend Team", slug="backend", is_active=True)

    # 2. Create Service
    services_url = reverse("api:service-list")
    srv_payload = {
        "name": "Payment API",
        "slug": "payment-api",
        "team_id": backend_team.id,
        "status": "healthy",
    }
    srv_resp = client.post(services_url, srv_payload, format="json")
    assert srv_resp.status_code == 201
    payment_service_id = srv_resp.json()["id"]

    # 3. Ingest first Alert
    alerts_url = reverse("api:alert-list")
    alert_payload = {
        "service_id": payment_service_id,
        "severity": "critical",
        "message": "HTTP 500 rate above 20%",
        "source": "prometheus",
    }
    a1_resp = client.post(alerts_url, alert_payload, format="json")
    assert a1_resp.status_code == 201
    a1_data = a1_resp.json()
    assert a1_data["service"]["id"] == payment_service_id
    assert a1_data["severity"] == "CRITICAL"
    assert a1_data["source"] == "prometheus"
    assert a1_data["message"] == "HTTP 500 rate above 20%"
    assert len(a1_data["fingerprint"]) == 64
    assert a1_data["received_at"] is not None

    # 4. Ingest identical Alert again
    a2_resp = client.post(alerts_url, alert_payload, format="json")
    assert a2_resp.status_code == 201
    a2_data = a2_resp.json()
    assert a2_data["id"] != a1_data["id"]
    assert a2_data["fingerprint"] == a1_data["fingerprint"]

    # 5. Nonexistent service rejected
    bad_srv_resp = client.post(
        alerts_url,
        {
            "service_id": 999999,
            "severity": "critical",
            "message": "Some alert",
            "source": "test",
        },
        format="json",
    )
    assert bad_srv_resp.status_code == 400
    assert "service_id" in bad_srv_resp.json()

    # 6. Invalid severity rejected
    bad_sev_resp = client.post(
        alerts_url,
        {
            "service_id": payment_service_id,
            "severity": "catastrophic",
            "message": "Some alert",
            "source": "test",
        },
        format="json",
    )
    assert bad_sev_resp.status_code == 400
    assert "severity" in bad_sev_resp.json()
