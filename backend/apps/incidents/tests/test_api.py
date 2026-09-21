import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.incidents.models import Incident
from apps.services.models import Service
from apps.users.models import Team, User


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def user():
    return User.objects.create(username="oncall_dev", email="oncall@example.com")


@pytest.fixture
def service():
    team = Team.objects.create(name="Checkout Team", slug="checkout")
    return Service.objects.create(name="Checkout Service", slug="checkout-service", team=team)


@pytest.fixture
def incident(service):
    return Incident.objects.create(
        service=service,
        title="Elevated failure rate in checkout flow",
        severity=Incident.Severity.CRITICAL,
        fingerprint="api_test_fp",
    )


@pytest.mark.django_db
def test_list_and_filter_incidents(client, service):
    """Verify GET /api/incidents/ lists and filters by status and severity."""
    i1 = Incident.objects.create(
        service=service,
        title="Incident One",
        severity=Incident.Severity.HIGH,
        fingerprint="fp_1",
        status=Incident.Status.TRIGGERED,
    )
    i2 = Incident.objects.create(
        service=service,
        title="Incident Two",
        severity=Incident.Severity.LOW,
        fingerprint="fp_2",
        status=Incident.Status.RESOLVED,
    )

    url = reverse("api:incident-list")
    resp = client.get(url)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    # Filter by status
    resp_trig = client.get(f"{url}?status=triggered")
    assert resp_trig.status_code == 200
    assert len(resp_trig.json()) == 1
    assert resp_trig.json()[0]["id"] == i1.id

    # Filter by severity
    resp_low = client.get(f"{url}?severity=low")
    assert resp_low.status_code == 200
    assert len(resp_low.json()) == 1
    assert resp_low.json()[0]["id"] == i2.id


@pytest.mark.django_db
def test_retrieve_incident_detail(client, incident):
    """Verify GET /api/incidents/{id}/ returns incident detail with service and alert count."""
    url = reverse("api:incident-detail", kwargs={"pk": incident.id})
    resp = client.get(url)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == incident.id
    assert data["title"] == incident.title
    assert data["service"]["slug"] == "checkout-service"
    assert data["status"] == "TRIGGERED"
    assert data["alert_count"] == 0


@pytest.mark.django_db
def test_acknowledge_endpoint(client, incident, user):
    """Verify POST /api/incidents/{id}/acknowledge/ performs transition."""
    client.force_authenticate(user=user)
    url = reverse("api:incident-acknowledge", kwargs={"pk": incident.id})
    resp = client.post(url)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ACKNOWLEDGED"
    assert data["acknowledged_at"] is not None

    # Idempotent second acknowledge
    resp2 = client.post(url)
    assert resp2.status_code == 200


@pytest.mark.django_db
def test_resolve_endpoint(client, incident, user):
    """Verify POST /api/incidents/{id}/resolve/ transitions to RESOLVED."""
    client.force_authenticate(user=user)
    url = reverse("api:incident-resolve", kwargs={"pk": incident.id})
    resp = client.post(url)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "RESOLVED"
    assert data["resolved_at"] is not None


@pytest.mark.django_db
def test_reopen_endpoint_and_conflict(client, incident, user):
    """Verify POST /api/incidents/{id}/reopen/ works for RESOLVED and rejects active incidents."""
    client.force_authenticate(user=user)
    reopen_url = reverse("api:incident-reopen", kwargs={"pk": incident.id})

    # Cannot reopen when currently TRIGGERED (409 Conflict)
    bad_resp = client.post(reopen_url)
    assert bad_resp.status_code == 409

    # Resolve first
    resolve_url = reverse("api:incident-resolve", kwargs={"pk": incident.id})
    client.post(resolve_url)

    # Reopen must succeed
    reopen_resp = client.post(reopen_url)
    assert reopen_resp.status_code == 200
    assert reopen_resp.json()["status"] == "TRIGGERED"


@pytest.mark.django_db
def test_events_timeline_endpoint(client, incident):
    """Verify GET /api/incidents/{id}/events/ returns read-only ordered timeline."""
    from apps.incidents.models import IncidentEvent

    IncidentEvent.objects.create(
        incident=incident,
        event_type=IncidentEvent.EventType.INCIDENT_TRIGGERED,
    )
    IncidentEvent.objects.create(
        incident=incident,
        event_type=IncidentEvent.EventType.INCIDENT_ACKNOWLEDGED,
    )

    url = reverse("api:incident-events", kwargs={"pk": incident.id})
    resp = client.get(url)
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 2
    assert events[0]["event_type"] == "INCIDENT_TRIGGERED"
    assert events[1]["event_type"] == "INCIDENT_ACKNOWLEDGED"


@pytest.mark.django_db
def test_direct_creation_and_mutation_prohibited(client, incident):
    """Verify POST /api/incidents/ and PATCH /api/incidents/{id}/ return 405 Method Not Allowed."""
    list_url = reverse("api:incident-list")
    post_resp = client.post(list_url, {"title": "Arbitrary incident"})
    assert post_resp.status_code == 405

    detail_url = reverse("api:incident-detail", kwargs={"pk": incident.id})
    patch_resp = client.patch(detail_url, {"status": "RESOLVED"})
    assert patch_resp.status_code == 405
