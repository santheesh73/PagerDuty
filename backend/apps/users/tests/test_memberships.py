import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.users.models import Team, TeamMembership, User


@pytest.fixture
def client():
    return APIClient()


@pytest.mark.django_db
def test_create_membership_via_api(client):
    """Verify creating a membership through POST /api/team-memberships/."""
    user = User.objects.create_user(username="alice")
    team = Team.objects.create(name="Backend Team", slug="backend")

    url = reverse("api:team-membership-list")
    payload = {
        "user_id": user.id,
        "team_id": team.id,
        "role": TeamMembership.Role.ENGINEER,
    }
    response = client.post(url, payload, format="json")
    assert response.status_code == 201
    data = response.json()
    assert data["role"] == "ENGINEER"
    assert data["user"]["username"] == "alice"
    assert data["team"]["slug"] == "backend"
    assert data["is_active"] is True


@pytest.mark.django_db
def test_duplicate_membership_rejected_via_api(client):
    """Verify that attempting to create an already existing membership returns 400."""
    user = User.objects.create_user(username="alice")
    team = Team.objects.create(name="Backend Team", slug="backend")
    TeamMembership.objects.create(user=user, team=team)

    url = reverse("api:team-membership-list")
    payload = {
        "user_id": user.id,
        "team_id": team.id,
        "role": TeamMembership.Role.LEAD,
    }
    response = client.post(url, payload, format="json")
    assert response.status_code == 400
    assert "non_field_errors" in response.json()


@pytest.mark.django_db
def test_invalid_role_rejected(client):
    """Verify that an unsupported role returns 400 validation error."""
    user = User.objects.create_user(username="alice")
    team = Team.objects.create(name="Backend Team", slug="backend")

    url = reverse("api:team-membership-list")
    payload = {
        "user_id": user.id,
        "team_id": team.id,
        "role": "SUPER_ADMIN",
    }
    response = client.post(url, payload, format="json")
    assert response.status_code == 400
    assert "role" in response.json()


@pytest.mark.django_db
def test_membership_for_inactive_user_rejected(client):
    """Verify that adding an inactive user to a team returns 400."""
    user = User.objects.create_user(username="inactive_alice", is_active=False)
    team = Team.objects.create(name="Backend Team", slug="backend")

    url = reverse("api:team-membership-list")
    payload = {
        "user_id": user.id,
        "team_id": team.id,
        "role": TeamMembership.Role.ENGINEER,
    }
    response = client.post(url, payload, format="json")
    assert response.status_code == 400
    assert "user_id" in response.json()


@pytest.mark.django_db
def test_membership_for_inactive_team_rejected(client):
    """Verify that adding a user to an inactive team returns 400."""
    user = User.objects.create_user(username="alice")
    team = Team.objects.create(name="Deprecated Team", slug="deprecated", is_active=False)

    url = reverse("api:team-membership-list")
    payload = {
        "user_id": user.id,
        "team_id": team.id,
        "role": TeamMembership.Role.ENGINEER,
    }
    response = client.post(url, payload, format="json")
    assert response.status_code == 400
    assert "team_id" in response.json()


@pytest.mark.django_db
def test_deactivate_membership_via_delete_and_patch(client):
    """Verify soft deactivation via DELETE and PATCH."""
    user = User.objects.create_user(username="alice")
    team = Team.objects.create(name="Backend Team", slug="backend")
    membership = TeamMembership.objects.create(user=user, team=team)

    url = reverse("api:team-membership-detail", kwargs={"pk": membership.id})

    # Test DELETE soft-deactivates
    response = client.delete(url)
    assert response.status_code == 204
    membership.refresh_from_db()
    assert membership.is_active is False

    # Test PATCH can re-activate
    patch_response = client.patch(url, {"is_active": True}, format="json")
    assert patch_response.status_code == 200
    membership.refresh_from_db()
    assert membership.is_active is True


@pytest.mark.django_db
def test_phase_1_full_acceptance_scenario(client):
    """
    Phase 1 Acceptance Test Scenario (Section 29):
    1. Create 3 users: Alice, Bob, Charlie
    2. Create 2 teams: Backend Team, SRE Team
    3. Add:
       - Alice -> Backend Team -> ENGINEER
       - Bob -> Backend Team -> LEAD
       - Charlie -> SRE Team -> RESPONDER
    4. GET Backend Team members -> [Alice, Bob]
    5. Attempt to add Alice to Backend Team again -> rejected cleanly (400)
    6. Deactivate Alice's membership
    7. Query active Backend Team members -> [Bob] only
    8. Confirm users remain valid independent entities
    9. Confirm GET /api/health/ returns 200
    """
    # 1. Create users
    alice = User.objects.create_user(username="alice", first_name="Alice", last_name="Smith")
    bob = User.objects.create_user(username="bob", first_name="Bob", last_name="Jones")
    charlie = User.objects.create_user(username="charlie", first_name="Charlie", last_name="Brown")

    # 2. Create teams
    backend_team = Team.objects.create(name="Backend Team", slug="backend")
    sre_team = Team.objects.create(name="SRE Team", slug="sre")

    # 3. Add memberships
    memberships_url = reverse("api:team-membership-list")

    r1 = client.post(
        memberships_url,
        {"user_id": alice.id, "team_id": backend_team.id, "role": TeamMembership.Role.ENGINEER},
        format="json",
    )
    assert r1.status_code == 201
    alice_membership_id = r1.json()["id"]

    r2 = client.post(
        memberships_url,
        {"user_id": bob.id, "team_id": backend_team.id, "role": TeamMembership.Role.LEAD},
        format="json",
    )
    assert r2.status_code == 201

    r3 = client.post(
        memberships_url,
        {"user_id": charlie.id, "team_id": sre_team.id, "role": TeamMembership.Role.RESPONDER},
        format="json",
    )
    assert r3.status_code == 201

    # 4. GET Backend Team members
    team_members_url = reverse("api:team-members", kwargs={"pk": backend_team.id})
    get_members_resp = client.get(team_members_url)
    assert get_members_resp.status_code == 200
    member_data = get_members_resp.json()
    assert len(member_data) == 2
    member_usernames = [m["user"]["username"] for m in member_data]
    assert "alice" in member_usernames
    assert "bob" in member_usernames

    # 5. Attempt duplicate membership for Alice on Backend Team
    dup_resp = client.post(
        memberships_url,
        {"user_id": alice.id, "team_id": backend_team.id, "role": TeamMembership.Role.ENGINEER},
        format="json",
    )
    assert dup_resp.status_code == 400

    # 6. Deactivate Alice's membership
    detail_url = reverse("api:team-membership-detail", kwargs={"pk": alice_membership_id})
    deact_resp = client.delete(detail_url)
    assert deact_resp.status_code == 204

    # 7. Query active Backend Team members
    active_members_resp = client.get(team_members_url, {"is_active": "true"})
    assert active_members_resp.status_code == 200
    active_members = active_members_resp.json()
    assert len(active_members) == 1
    assert active_members[0]["user"]["username"] == "bob"

    # 8. Confirm users remain valid independent entities
    assert User.objects.filter(username="alice").exists()
    assert User.objects.filter(username="bob").exists()
    assert User.objects.filter(username="charlie").exists()

    # 9. Confirm health endpoint still works
    health_url = reverse("api:health_check")
    health_resp = client.get(health_url)
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "ok"
