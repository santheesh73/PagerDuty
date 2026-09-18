import pytest
from django.urls import reverse
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
def test_django_boots_and_settings_configured():
    """Verify that Django boots and settings can be inspected."""
    from django.conf import settings
    assert settings.configured
    assert settings.USE_TZ is True
    assert "rest_framework" in settings.INSTALLED_APPS
    assert "corsheaders" in settings.INSTALLED_APPS


@pytest.mark.django_db
def test_health_endpoint_returns_200(api_client):
    """Verify GET /api/health/ returns HTTP 200."""
    url = reverse("api:health_check")
    response = api_client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_health_response_schema(api_client):
    """Verify GET /api/health/ matches the expected infrastructure response schema."""
    url = reverse("api:health_check")
    response = api_client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data.get("status") == "ok"
    assert "dependencies" in data
    assert isinstance(data["dependencies"], dict)
    assert "database" in data["dependencies"]
    assert "redis" in data["dependencies"]
