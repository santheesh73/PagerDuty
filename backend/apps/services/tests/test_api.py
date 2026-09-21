import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.services.models import Service
from apps.users.models import Team


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def team():
    return Team.objects.create(name="Backend Team", slug="backend", is_active=True)


@pytest.mark.django_db
def test_list_services(client, team):
    """Verify GET /api/services/ returns service list."""
    Service.objects.create(name="Service Alpha", slug="alpha", team=team)
    Service.objects.create(name="Service Beta", slug="beta", team=team)

    url = reverse("api:service-list")
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    names = [s["name"] for s in data]
    assert "Service Alpha" in names
    assert "Service Beta" in names


@pytest.mark.django_db
def test_retrieve_service(client, team):
    """Verify GET /api/services/{id}/ returns full service details."""
    service = Service.objects.create(
        name="Payment API",
        slug="payment-api",
        description="Processes payments",
        team=team,
        status=Service.Status.HEALTHY,
    )
    url = reverse("api:service-detail", kwargs={"pk": service.id})
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Payment API"
    assert data["slug"] == "payment-api"
    assert data["team"]["slug"] == "backend"
    assert data["status"] == "HEALTHY"


@pytest.mark.django_db
def test_create_service(client, team):
    """Verify POST /api/services/ creates a new Service."""
    url = reverse("api:service-list")
    payload = {
        "name": "Auth API",
        "slug": "auth-api",
        "description": "Authentication microservice",
        "team_id": team.id,
        "status": "HEALTHY",
    }
    response = client.post(url, payload, format="json")
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Auth API"
    assert data["slug"] == "auth-api"
    assert data["team"]["name"] == "Backend Team"
    assert Service.objects.filter(slug="auth-api").exists()


@pytest.mark.django_db
def test_create_service_duplicate_slug_rejected(client, team):
    """Verify that duplicate service slugs return 400."""
    Service.objects.create(name="Existing", slug="duplicate-slug", team=team)
    url = reverse("api:service-list")
    payload = {
        "name": "New Service",
        "slug": "duplicate-slug",
        "team_id": team.id,
    }
    response = client.post(url, payload, format="json")
    assert response.status_code == 400
    assert "slug" in response.json()


@pytest.mark.django_db
def test_create_service_inactive_team_rejected(client):
    """Verify that assigning an active service to an inactive team returns 400."""
    inactive_team = Team.objects.create(name="Deprecated Team", slug="deprecated", is_active=False)
    url = reverse("api:service-list")
    payload = {
        "name": "Orphaned Service",
        "slug": "orphaned",
        "team_id": inactive_team.id,
        "is_active": True,
    }
    response = client.post(url, payload, format="json")
    assert response.status_code == 400
    assert "team_id" in response.json()


@pytest.mark.django_db
def test_update_service(client, team):
    """Verify PATCH /api/services/{id}/ updates status and description."""
    service = Service.objects.create(name="Worker API", slug="worker-api", team=team)
    url = reverse("api:service-detail", kwargs={"pk": service.id})
    response = client.patch(url, {"status": "DEGRADED", "description": "High latency"}, format="json")
    assert response.status_code == 200
    service.refresh_from_db()
    assert service.status == "DEGRADED"
    assert service.description == "High latency"


@pytest.mark.django_db
def test_filter_services_by_team_and_status(client, team):
    """Verify query parameter filtering on /api/services/."""
    other_team = Team.objects.create(name="Platform Team", slug="platform")
    Service.objects.create(name="S1", slug="s1", team=team, status=Service.Status.HEALTHY)
    Service.objects.create(name="S2", slug="s2", team=team, status=Service.Status.DOWN)
    Service.objects.create(name="S3", slug="s3", team=other_team, status=Service.Status.HEALTHY)

    url = reverse("api:service-list")

    # Filter by team
    r_team = client.get(url, {"team": team.id})
    assert r_team.status_code == 200
    assert len(r_team.json()) == 2

    # Filter by status
    r_status = client.get(url, {"status": "DOWN"})
    assert r_status.status_code == 200
    assert len(r_status.json()) == 1
    assert r_status.json()[0]["slug"] == "s2"


@pytest.mark.django_db
def test_retrieve_nonexistent_service_returns_404(client):
    """Verify 404 on nonexistent service request."""
    url = reverse("api:service-detail", kwargs={"pk": 99999})
    response = client.get(url)
    assert response.status_code == 404
