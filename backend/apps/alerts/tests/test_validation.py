import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.services.models import Service
from apps.users.models import Team


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def active_service():
    team = Team.objects.create(name="Backend Team", slug="backend", is_active=True)
    return Service.objects.create(name="Payment API", slug="payment-api", team=team, is_active=True)


@pytest.mark.django_db
def test_unknown_service_rejected(client):
    """Verify alert ingestion with nonexistent service_id returns 400."""
    url = reverse("api:alert-list")
    payload = {
        "service_id": 99999,
        "severity": "CRITICAL",
        "message": "Out of memory",
        "source": "prometheus",
    }
    response = client.post(url, payload, format="json")
    assert response.status_code == 400
    assert "service_id" in response.json()


@pytest.mark.django_db
def test_inactive_service_rejected(client):
    """Verify alert ingestion for inactive service is rejected with validation error."""
    team = Team.objects.create(name="Old Team", slug="old-team")
    inactive_srv = Service.objects.create(name="Old API", slug="old-api", team=team, is_active=False)

    url = reverse("api:alert-list")
    payload = {
        "service_id": inactive_srv.id,
        "severity": "CRITICAL",
        "message": "Process failed",
        "source": "manual",
    }
    response = client.post(url, payload, format="json")
    assert response.status_code == 400
    assert "service_id" in response.json()
    assert "inactive" in str(response.json()["service_id"]).lower()


@pytest.mark.django_db
def test_invalid_severity_rejected(client, active_service):
    """Verify alert ingestion with unsupported severity returns 400."""
    url = reverse("api:alert-list")
    payload = {
        "service_id": active_service.id,
        "severity": "SUPER_DISASTER",
        "message": "Failure",
        "source": "prometheus",
    }
    response = client.post(url, payload, format="json")
    assert response.status_code == 400
    assert "severity" in response.json()


@pytest.mark.django_db
def test_blank_message_rejected(client, active_service):
    """Verify blank or whitespace message is rejected."""
    url = reverse("api:alert-list")
    payload = {
        "service_id": active_service.id,
        "severity": "HIGH",
        "message": "   ",
        "source": "prometheus",
    }
    response = client.post(url, payload, format="json")
    assert response.status_code == 400
    assert "message" in response.json()


@pytest.mark.django_db
def test_blank_source_rejected(client, active_service):
    """Verify blank or whitespace source is rejected."""
    url = reverse("api:alert-list")
    payload = {
        "service_id": active_service.id,
        "severity": "HIGH",
        "message": "Disk failure",
        "source": "   ",
    }
    response = client.post(url, payload, format="json")
    assert response.status_code == 400
    assert "source" in response.json()
