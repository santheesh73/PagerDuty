import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.escalation.models import EscalationLevel, EscalationPolicy
from apps.users.models import Team, TeamMembership

User = get_user_model()


@pytest.fixture
def api_env():
    client = APIClient()
    team_a = Team.objects.create(name="Team A", slug="team-a")
    team_b = Team.objects.create(name="Team B", slug="team-b")

    user_a = User.objects.create_user(username="user_a", email="user_a@example.com")
    user_b = User.objects.create_user(username="user_b", email="user_b@example.com")

    TeamMembership.objects.create(user=user_a, team=team_a, role=TeamMembership.Role.ENGINEER)
    TeamMembership.objects.create(user=user_b, team=team_b, role=TeamMembership.Role.ENGINEER)

    policy = EscalationPolicy.objects.create(name="Policy A", slug="policy-a", team=team_a, is_active=True)
    level_1 = EscalationLevel.objects.create(
        policy=policy,
        order=1,
        target_type=EscalationLevel.TargetType.CURRENT_ON_CALL,
        wait_minutes=10,
    )

    return {
        "client": client,
        "team_a": team_a,
        "team_b": team_b,
        "user_a": user_a,
        "user_b": user_b,
        "policy": policy,
        "level_1": level_1,
    }


@pytest.mark.django_db
def test_list_and_retrieve_escalation_policies(api_env):
    client = api_env["client"]
    resp = client.get("/api/escalation-policies/")
    assert resp.status_code == 200
    assert len(resp.data) >= 1

    detail_resp = client.get(f"/api/escalation-policies/{api_env['policy'].id}/")
    assert detail_resp.status_code == 200
    assert detail_resp.data["name"] == "Policy A"
    assert len(detail_resp.data["levels"]) == 1


@pytest.mark.django_db
def test_create_escalation_policy(api_env):
    client = api_env["client"]
    payload = {
        "name": "New Policy",
        "slug": "new-policy",
        "team": api_env["team_a"].id,
        "is_active": True,
    }
    resp = client.post("/api/escalation-policies/", payload, format="json")
    assert resp.status_code == 201
    assert resp.data["slug"] == "new-policy"


@pytest.mark.django_db
def test_create_escalation_level_valid_and_duplicate_order_rejected(api_env):
    client = api_env["client"]
    # 1. Valid level 2
    payload_valid = {
        "policy": api_env["policy"].id,
        "order": 2,
        "target_type": "USER",
        "target_user": api_env["user_a"].id,
        "wait_minutes": 15,
    }
    resp1 = client.post("/api/escalation-levels/", payload_valid, format="json")
    assert resp1.status_code == 201
    assert resp1.data["order"] == 2

    # 2. Duplicate order (order=1 already exists)
    payload_dup = {
        "policy": api_env["policy"].id,
        "order": 1,
        "target_type": "USER",
        "target_user": api_env["user_a"].id,
        "wait_minutes": 15,
    }
    resp2 = client.post("/api/escalation-levels/", payload_dup, format="json")
    assert resp2.status_code == 400


@pytest.mark.django_db
def test_create_escalation_level_cross_team_user_rejected(api_env):
    client = api_env["client"]
    # User B belongs to Team B, while policy belongs to Team A
    payload = {
        "policy": api_env["policy"].id,
        "order": 2,
        "target_type": "USER",
        "target_user": api_env["user_b"].id,
        "wait_minutes": 15,
    }
    resp = client.post("/api/escalation-levels/", payload, format="json")
    assert resp.status_code == 400
    assert "target_user" in resp.data
