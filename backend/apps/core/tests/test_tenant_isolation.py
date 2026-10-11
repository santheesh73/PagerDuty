"""Tenant isolation: one team must never see or touch another team's data."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Membership
from tests.factories import (
    IncidentFactory,
    MembershipFactory,
    ServiceFactory,
    TeamFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def two_teams():
    team_a, team_b = TeamFactory(), TeamFactory()
    alice = UserFactory()
    MembershipFactory(user=alice, team=team_a, role=Membership.Role.ADMIN)
    svc_a = ServiceFactory(team=team_a)
    svc_b = ServiceFactory(team=team_b)
    inc_a = IncidentFactory(service=svc_a)
    inc_b = IncidentFactory(service=svc_b)
    client = APIClient()
    client.force_authenticate(alice)
    return client, inc_a, inc_b, svc_b


def test_list_excludes_other_teams(two_teams):
    client, inc_a, inc_b, _ = two_teams
    body = client.get("/api/v1/incidents/").json()
    ids = {row["id"] for row in body["results"]}
    assert inc_a.pk in ids
    assert inc_b.pk not in ids, "LEAK: cross-team incident listed"


def test_detail_of_other_team_denied(two_teams):
    client, _, inc_b, _ = two_teams
    assert client.get(f"/api/v1/incidents/{inc_b.pk}/").status_code in (403, 404)


def test_action_on_other_team_denied(two_teams):
    client, _, inc_b, _ = two_teams
    r = client.post(f"/api/v1/incidents/{inc_b.pk}/acknowledge/")
    assert r.status_code in (403, 404), f"LEAK: acted on other team, got {r.status_code}"
    inc_b.refresh_from_db()
    assert inc_b.status == "triggered"


def test_other_team_service_denied(two_teams):
    client, _, _, svc_b = two_teams
    assert client.get(f"/api/v1/services/{svc_b.pk}/").status_code in (403, 404)


def test_cannot_rotate_other_team_key(two_teams):
    client, _, _, svc_b = two_teams
    before = svc_b.integration_key_hash
    assert client.post(f"/api/v1/services/{svc_b.pk}/rotate-key/").status_code in (403, 404)
    svc_b.refresh_from_db()
    assert svc_b.integration_key_hash == before, "LEAK: rotated another team's key"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/incidents/",
        "/api/v1/services/",
        "/api/v1/notifications/",
        "/api/v1/analytics/summary/",
        "/api/v1/oncalls/",
        "/api/v1/schedules/",
        "/api/v1/escalation-policies/",
        "/api/v1/teams/",
    ],
)
def test_anonymous_denied(path):
    r = APIClient().get(path)
    assert r.status_code in (401, 403), f"OPEN TO ANON: {path} -> {r.status_code}"
