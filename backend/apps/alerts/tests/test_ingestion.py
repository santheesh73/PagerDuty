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
    assert data["incident_id"] is not None


@pytest.mark.django_db
def test_duplicate_alert_ingestion_generates_matching_fingerprint(client, service):
    """
    Verify that identical alerts sent twice are both persisted
    and attach to the exact same active incident.
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
    assert alert1["incident_id"] is not None
    assert alert1["incident_id"] == alert2["incident_id"]


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


@pytest.mark.django_db
def test_phase_3_golden_acceptance_scenario(client):
    """
    Section 56: Golden Phase 3 Acceptance Scenario.
    Steps:
    1. POST /api/alerts/ -> Alert #1 created, Incident #1 created (status=TRIGGERED, timeline: TRIGGERED, ATTACHED)
    2. POST exact same Alert -> Alert #2 created, attaches to Incident #1, timeline gains ALERT_ATTACHED (total 3 events)
    3. POST /api/incidents/{id}/acknowledge/ -> TRIGGERED -> ACKNOWLEDGED, acknowledged_at set, timeline gains ACKNOWLEDGED
    4. POST same acknowledge again -> idempotent success, timestamp unchanged, no duplicate event
    5. POST /api/incidents/{id}/resolve/ -> ACKNOWLEDGED -> RESOLVED, resolved_at set, timeline gains RESOLVED
    6. Submit identical alert again -> Alert #3 created, Incident #2 created (does NOT attach to resolved Incident #1)
    7. Try reopening Incident #1 while Incident #2 is active -> clean 409 conflict
    8. Resolve Incident #2, then reopen Incident #1 -> Incident #1 returns to TRIGGERED, reset timestamps, timeline gains REOPENED
    """
    # Setup team and service
    team = Team.objects.create(name="Backend Team", slug="backend-golden", is_active=True)
    service = Service.objects.create(name="Payment API", slug="payment-api-golden", team=team, is_active=True)

    alerts_url = reverse("api:alert-list")
    alert_payload = {
        "service_id": service.id,
        "severity": "critical",
        "message": "HTTP 500 rate above 20%",
        "source": "prometheus",
    }

    # Step 1: Ingest initial alert
    resp_a1 = client.post(alerts_url, alert_payload, format="json")
    assert resp_a1.status_code == 201
    data_a1 = resp_a1.json()
    inc1_id = data_a1["incident_id"]
    assert inc1_id is not None

    inc1_url = reverse("api:incident-detail", kwargs={"pk": inc1_id})
    inc1_resp = client.get(inc1_url)
    assert inc1_resp.status_code == 200
    inc1_data = inc1_resp.json()
    assert inc1_data["status"] == "TRIGGERED"
    assert inc1_data["severity"] == "CRITICAL"
    assert inc1_data["service"]["id"] == service.id
    assert inc1_data["assigned_user"] is None
    assert inc1_data["resolved_at"] is None
    assert inc1_data["alert_count"] == 1

    events_url_1 = reverse("api:incident-events", kwargs={"pk": inc1_id})
    events_1 = client.get(events_url_1).json()
    assert len(events_1) == 2
    assert events_1[0]["event_type"] == "INCIDENT_TRIGGERED"
    assert events_1[1]["event_type"] == "ALERT_ATTACHED"

    # Step 2: Post exact same alert again
    resp_a2 = client.post(alerts_url, alert_payload, format="json")
    assert resp_a2.status_code == 201
    data_a2 = resp_a2.json()
    assert data_a2["id"] != data_a1["id"]
    assert data_a2["incident_id"] == inc1_id

    events_2 = client.get(events_url_1).json()
    assert len(events_2) == 3
    assert events_2[2]["event_type"] == "ALERT_ATTACHED"

    # Step 3: Acknowledge Incident #1
    ack_url_1 = reverse("api:incident-acknowledge", kwargs={"pk": inc1_id})
    ack_resp_1 = client.post(ack_url_1)
    assert ack_resp_1.status_code == 200
    ack_data_1 = ack_resp_1.json()
    assert ack_data_1["status"] == "ACKNOWLEDGED"
    assert ack_data_1["acknowledged_at"] is not None
    orig_ack_time = ack_data_1["acknowledged_at"]

    events_3 = client.get(events_url_1).json()
    assert len(events_3) == 4
    assert events_3[3]["event_type"] == "INCIDENT_ACKNOWLEDGED"

    # Step 4: Acknowledge again (idempotent)
    ack_resp_again = client.post(ack_url_1)
    assert ack_resp_again.status_code == 200
    assert ack_resp_again.json()["acknowledged_at"] == orig_ack_time
    assert len(client.get(events_url_1).json()) == 4

    # Step 5: Resolve Incident #1
    resolve_url_1 = reverse("api:incident-resolve", kwargs={"pk": inc1_id})
    resolve_resp_1 = client.post(resolve_url_1)
    assert resolve_resp_1.status_code == 200
    assert resolve_resp_1.json()["status"] == "RESOLVED"
    assert resolve_resp_1.json()["resolved_at"] is not None

    events_5 = client.get(events_url_1).json()
    assert len(events_5) == 5
    assert events_5[4]["event_type"] == "INCIDENT_RESOLVED"

    # Step 6: Ingest identical alert again (must create Incident #2, NOT attach to resolved #1)
    resp_a3 = client.post(alerts_url, alert_payload, format="json")
    assert resp_a3.status_code == 201
    data_a3 = resp_a3.json()
    inc2_id = data_a3["incident_id"]
    assert inc2_id is not None
    assert inc2_id != inc1_id

    # Step 7: Try reopening Incident #1 while Incident #2 is active -> clean 409 conflict
    reopen_url_1 = reverse("api:incident-reopen", kwargs={"pk": inc1_id})
    reopen_conflict_resp = client.post(reopen_url_1)
    assert reopen_conflict_resp.status_code == 409
    assert "active incident already exists" in reopen_conflict_resp.json()["detail"]

    # Step 8: Resolve Incident #2, then reopen Incident #1
    resolve_url_2 = reverse("api:incident-resolve", kwargs={"pk": inc2_id})
    client.post(resolve_url_2)

    reopen_resp_1 = client.post(reopen_url_1)
    assert reopen_resp_1.status_code == 200
    reopened_data = reopen_resp_1.json()
    assert reopened_data["status"] == "TRIGGERED"
    assert reopened_data["triggered_at"] is not None
    assert reopened_data["acknowledged_at"] is None
    assert reopened_data["resolved_at"] is None

    events_final = client.get(events_url_1).json()
    assert len(events_final) == 6
    assert events_final[5]["event_type"] == "INCIDENT_REOPENED"

