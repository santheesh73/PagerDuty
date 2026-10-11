"""List endpoints must cost the same number of queries however many rows they return."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.accounts.models import Membership
from tests.factories import (
    EscalationPolicyFactory,
    MembershipFactory,
    ScheduleFactory,
    ScheduleLayerFactory,
    TeamFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client():
    team = TeamFactory()
    admin = UserFactory()
    MembershipFactory(user=admin, team=team, role=Membership.Role.ADMIN)
    client = APIClient()
    client.force_authenticate(admin)
    return client, team


def count_queries(client: APIClient, path: str) -> int:
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(path)
    assert response.status_code == 200
    return len(ctx)


def grow_schedules(team, n: int) -> None:
    for _ in range(n):
        users = [
            MembershipFactory(team=team, role=Membership.Role.RESPONDER).user for _ in range(3)
        ]
        ScheduleLayerFactory(schedule=ScheduleFactory(team=team), users=users)


def grow_policies(team, n: int) -> None:
    for _ in range(n):
        EscalationPolicyFactory(team=team)


def test_the_schedules_list_does_not_query_per_row(admin_client) -> None:
    client, team = admin_client
    grow_schedules(team, 1)
    few = count_queries(client, "/api/v1/schedules/")
    grow_schedules(team, 12)
    many = count_queries(client, "/api/v1/schedules/")
    assert many == few, f"schedules list: {few} queries for 1 row, {many} for 13"


def test_the_on_call_overview_does_not_query_per_policy(admin_client) -> None:
    client, team = admin_client
    grow_policies(team, 1)
    few = count_queries(client, "/api/v1/oncalls/")
    grow_policies(team, 12)
    many = count_queries(client, "/api/v1/oncalls/")
    assert many == few, f"/oncalls/: {few} queries for 1 policy, {many} for 13"
