import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.users.models import Team, TeamMembership, User


@pytest.fixture
def client():
    return APIClient()


@pytest.mark.django_db
def test_list_users(client):
    """Verify listing users through /api/users/."""
    User.objects.create_user(username="alice", email="alice@example.com")
    User.objects.create_user(username="bob", email="bob@example.com")

    url = reverse("api:user-list")
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    usernames = [u["username"] for u in data]
    assert "alice" in usernames
    assert "bob" in usernames


@pytest.mark.django_db
def test_retrieve_user(client):
    """Verify retrieving a specific user through /api/users/{id}/."""
    user = User.objects.create_user(
        username="alice",
        first_name="Alice",
        last_name="Smith",
        email="alice@example.com",
    )
    url = reverse("api:user-detail", kwargs={"pk": user.id})
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "alice"
    assert data["name"] == "Alice Smith"
    assert data["email"] == "alice@example.com"


@pytest.mark.django_db
def test_retrieve_nonexistent_user_returns_404(client):
    """Verify 404 response when querying nonexistent user."""
    url = reverse("api:user-detail", kwargs={"pk": 99999})
    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_filter_users_by_team(client):
    """Verify filtering users by team membership via ?team=<team_id>."""
    alice = User.objects.create_user(username="alice")
    bob = User.objects.create_user(username="bob")
    team = Team.objects.create(name="Backend Team", slug="backend")
    TeamMembership.objects.create(user=alice, team=team)

    url = reverse("api:user-list")
    response = client.get(url, {"team": team.id})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["username"] == "alice"
    assert bob.username not in [u["username"] for u in data]


@pytest.mark.django_db
def test_create_team(client):
    """Verify creating a new Team through POST /api/teams/."""
    url = reverse("api:team-list")
    payload = {
        "name": "Site Reliability Engineering",
        "slug": "sre",
        "description": "On-call response and platform reliability",
        "is_active": True,
    }
    response = client.post(url, payload, format="json")
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == payload["name"]
    assert data["slug"] == payload["slug"]
    assert data["member_count"] == 0
    assert Team.objects.filter(slug="sre").exists()


@pytest.mark.django_db
def test_create_team_duplicate_slug_rejected(client):
    """Verify duplicate team slug returns 400 bad request."""
    Team.objects.create(name="First Team", slug="duplicate-slug")
    url = reverse("api:team-list")
    payload = {
        "name": "Second Team",
        "slug": "duplicate-slug",
    }
    response = client.post(url, payload, format="json")
    assert response.status_code == 400
    assert "slug" in response.json()


@pytest.mark.django_db
def test_update_team(client):
    """Verify partial update of Team via PATCH /api/teams/{id}/."""
    team = Team.objects.create(name="Initial Name", slug="team-slug")
    url = reverse("api:team-detail", kwargs={"pk": team.id})
    response = client.patch(url, {"name": "Updated Name"}, format="json")
    assert response.status_code == 200
    team.refresh_from_db()
    assert team.name == "Updated Name"


@pytest.mark.django_db
def test_retrieve_nonexistent_team_returns_404(client):
    """Verify 404 response when querying nonexistent team."""
    url = reverse("api:team-detail", kwargs={"pk": 99999})
    response = client.get(url)
    assert response.status_code == 404
