from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.escalation.models import EscalationLevel, EscalationPolicy
from apps.incidents.models import Incident
from apps.services.models import Service
from apps.users.models import Team, User


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def analytics_setup(db):
    team = Team.objects.create(name="Platform Ops", slug="platform-ops", is_active=True)
    user = User.objects.create_user(username="testuser", email="test@example.com")
    service1 = Service.objects.create(name="Auth API", slug="auth-api", team=team)
    service2 = Service.objects.create(name="Billing API", slug="billing-api", team=team)

    now = timezone.now()

    # Incident 1: Critical, acknowledged after 120s, resolved after 600s
    inc1 = Incident.objects.create(
        service=service1,
        title="Auth Down",
        severity=Incident.Severity.CRITICAL,
        status=Incident.Status.RESOLVED,
        fingerprint="fp-1",
        triggered_at=now - timedelta(seconds=700),
        acknowledged_at=now - timedelta(seconds=580),
        resolved_at=now - timedelta(seconds=100),
    )

    # Incident 2: High, acknowledged after 180s, active (not resolved)
    inc2 = Incident.objects.create(
        service=service1,
        title="Auth High Latency",
        severity=Incident.Severity.HIGH,
        status=Incident.Status.ACKNOWLEDGED,
        fingerprint="fp-2",
        triggered_at=now - timedelta(seconds=400),
        acknowledged_at=now - timedelta(seconds=220),
        resolved_at=None,
    )

    # Incident 3: Medium, triggered (unacknowledged, unresolved)
    inc3 = Incident.objects.create(
        service=service2,
        title="Billing Slow",
        severity=Incident.Severity.MEDIUM,
        status=Incident.Status.TRIGGERED,
        fingerprint="fp-3",
        triggered_at=now - timedelta(seconds=200),
        acknowledged_at=None,
        resolved_at=None,
    )

    return {
        "team": team,
        "user": user,
        "service1": service1,
        "service2": service2,
        "incidents": [inc1, inc2, inc3],
    }


@pytest.mark.django_db
def test_analytics_summary(api_client, analytics_setup):
    response = api_client.get("/api/analytics/summary/?range=7d")
    assert response.status_code == 200
    data = response.json()

    assert data["incident_count"] == 3
    assert data["active_incidents"] == 2
    assert data["critical_incidents"] == 1
    # MTTA: (120s + 180s) / 2 = 150.0s
    assert data["mtta_seconds"] == 150.0
    # MTTR: exactly 600.0s for the single resolved incident
    assert data["mttr_seconds"] == 600.0


@pytest.mark.django_db
def test_analytics_summary_empty_metrics(api_client, db):
    response = api_client.get("/api/analytics/summary/")
    assert response.status_code == 200
    data = response.json()
    assert data["incident_count"] == 0
    assert data["active_incidents"] == 0
    assert data["mtta_seconds"] is None
    assert data["mttr_seconds"] is None


@pytest.mark.django_db
def test_analytics_summary_null_semantics_unacknowledged_and_unresolved(api_client, db):
    """
    Verify Golden Metric Rule:
    When incidents exist but none are acknowledged, mtta_seconds is None (NOT 0.0).
    When incidents exist and are acknowledged but none are resolved, mttr_seconds is None (NOT 0.0).
    """
    team = Team.objects.create(name="SRE Team", slug="sre-team", is_active=True)
    service = Service.objects.create(name="Gateway", slug="gateway", team=team)
    now = timezone.now()

    # Create only triggered unacknowledged incident
    inc = Incident.objects.create(
        service=service,
        title="Gateway 502",
        severity=Incident.Severity.CRITICAL,
        status=Incident.Status.TRIGGERED,
        fingerprint="gw-fp",
        triggered_at=now - timedelta(minutes=5),
        acknowledged_at=None,
        resolved_at=None,
    )

    resp1 = api_client.get("/api/analytics/summary/")
    assert resp1.status_code == 200
    d1 = resp1.json()
    assert d1["incident_count"] == 1
    assert d1["active_incidents"] == 1
    assert d1["mtta_seconds"] is None
    assert d1["mttr_seconds"] is None

    # Now acknowledge the incident (acknowledged after 60s), but keep it active/unresolved
    inc.status = Incident.Status.ACKNOWLEDGED
    inc.acknowledged_at = inc.triggered_at + timedelta(seconds=60)
    inc.save(update_fields=["status", "acknowledged_at"])

    resp2 = api_client.get("/api/analytics/summary/")
    assert resp2.status_code == 200
    d2 = resp2.json()
    assert d2["incident_count"] == 1
    assert d2["active_incidents"] == 1
    assert d2["mtta_seconds"] == 60.0
    assert d2["mttr_seconds"] is None


@pytest.mark.django_db
def test_analytics_incidents_by_service(api_client, analytics_setup):
    response = api_client.get("/api/analytics/incidents-by-service/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    # Auth API has 2, Billing API has 1
    assert data[0]["service_name"] == "Auth API"
    assert data[0]["count"] == 2
    assert data[1]["service_name"] == "Billing API"
    assert data[1]["count"] == 1


@pytest.mark.django_db
def test_analytics_severity_distribution(api_client, analytics_setup):
    response = api_client.get("/api/analytics/severity-distribution/")
    assert response.status_code == 200
    data = response.json()
    # Canonical order: critical, high, medium, low
    sev_map = {item["severity"]: item["count"] for item in data}
    assert sev_map["critical"] == 1
    assert sev_map["high"] == 1
    assert sev_map["medium"] == 1
    assert sev_map["low"] == 0


@pytest.mark.django_db
def test_analytics_trend(api_client, analytics_setup):
    response = api_client.get("/api/analytics/trend/?range=7d")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 7
    total = sum(item["count"] for item in data)
    assert total == 3


@pytest.mark.django_db
def test_reorder_escalation_levels(api_client, db):
    team = Team.objects.create(name="DevOps", slug="devops", is_active=True)
    policy = EscalationPolicy.objects.create(name="Primary Policy", slug="primary-policy", team=team)
    level1 = EscalationLevel.objects.create(policy=policy, order=1, wait_minutes=5)
    level2 = EscalationLevel.objects.create(policy=policy, order=2, wait_minutes=10)
    level3 = EscalationLevel.objects.create(policy=policy, order=3, wait_minutes=15)

    # Reorder: level3, level1, level2
    response = api_client.post(
        f"/api/escalation-policies/{policy.id}/reorder-levels/",
        {"level_ids": [level3.id, level1.id, level2.id]},
        format="json",
    )
    assert response.status_code == 200

    level3.refresh_from_db()
    level1.refresh_from_db()
    level2.refresh_from_db()

    assert level3.order == 1
    assert level1.order == 2
    assert level2.order == 3
