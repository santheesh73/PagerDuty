from datetime import UTC, datetime

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.scheduling.models import Schedule, ScheduleRotation
from apps.users.models import Team, TeamMembership, User


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def scheduling_api_setup(db):
    team = Team.objects.create(name="Backend Team", slug="backend-team")
    other_team = Team.objects.create(name="Platform Team", slug="platform-team")
    alice = User.objects.create_user(username="alice", first_name="Alice", last_name="Smith")
    bob = User.objects.create_user(username="bob", first_name="Bob", last_name="Jones")
    charlie = User.objects.create_user(username="charlie", first_name="Charlie")
    TeamMembership.objects.create(team=team, user=alice)
    TeamMembership.objects.create(team=team, user=bob)
    TeamMembership.objects.create(team=other_team, user=charlie)

    schedule = Schedule.objects.create(
        name="Backend Primary",
        slug="backend-primary",
        team=team,
        timezone="UTC",
        is_primary=True,
        is_active=True,
    )

    # Alice: 09:00 - 17:00 Base
    r1 = ScheduleRotation.objects.create(
        schedule=schedule,
        user=alice,
        start_time=datetime(2026, 9, 21, 9, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 9, 21, 17, 0, 0, tzinfo=UTC),
        is_override=False,
    )

    # Bob: 12:00 - 14:00 Override
    r2 = ScheduleRotation.objects.create(
        schedule=schedule,
        user=bob,
        start_time=datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 9, 21, 14, 0, 0, tzinfo=UTC),
        is_override=True,
    )

    return {
        "team": team,
        "other_team": other_team,
        "alice": alice,
        "bob": bob,
        "charlie": charlie,
        "schedule": schedule,
        "rotation_base": r1,
        "rotation_override": r2,
    }


@pytest.mark.django_db
def test_schedule_list_and_filter(api_client, scheduling_api_setup):
    res = api_client.get("/api/schedules/")
    assert res.status_code == status.HTTP_200_OK
    assert len(res.data) >= 1

    # Filter by team
    res_filtered = api_client.get(f"/api/schedules/?team={scheduling_api_setup['team'].id}")
    assert res_filtered.status_code == status.HTTP_200_OK
    assert len(res_filtered.data) == 1

    # Filter by is_primary
    res_primary = api_client.get("/api/schedules/?is_primary=true")
    assert res_primary.status_code == status.HTTP_200_OK
    assert all(s["is_primary"] is True for s in res_primary.data)


@pytest.mark.django_db
def test_schedule_create_and_validation(api_client, scheduling_api_setup):
    team = scheduling_api_setup["team"]

    # 1. Reject duplicate active primary schedule for same team
    payload = {
        "name": "Backend Secondary",
        "slug": "backend-secondary",
        "team": team.id,
        "timezone": "UTC",
        "is_primary": True,
        "is_active": True,
    }
    res = api_client.post("/api/schedules/", payload, format="json")
    assert res.status_code == status.HTTP_400_BAD_REQUEST

    # 2. Reject invalid timezone
    payload["is_primary"] = False
    payload["timezone"] = "Invalid/Zone"
    res_tz = api_client.post("/api/schedules/", payload, format="json")
    assert res_tz.status_code == status.HTTP_400_BAD_REQUEST

    # 3. Create valid secondary schedule
    payload["timezone"] = "UTC"
    res_valid = api_client.post("/api/schedules/", payload, format="json")
    assert res_valid.status_code == status.HTTP_201_CREATED
    assert res_valid.data["slug"] == "backend-secondary"


@pytest.mark.django_db
def test_schedule_patch_update(api_client, scheduling_api_setup):
    schedule = scheduling_api_setup["schedule"]
    res = api_client.patch(f"/api/schedules/{schedule.id}/", {"name": "Backend Tier 1 Primary"}, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert res.data["name"] == "Backend Tier 1 Primary"


@pytest.mark.django_db
def test_rotation_list_and_filter(api_client, scheduling_api_setup):
    res = api_client.get("/api/schedule-rotations/")
    assert res.status_code == status.HTTP_200_OK
    assert len(res.data) >= 2

    # Filter by override
    res_override = api_client.get("/api/schedule-rotations/?is_override=true")
    assert res_override.status_code == status.HTTP_200_OK
    assert all(r["is_override"] is True for r in res_override.data)


@pytest.mark.django_db
def test_rotation_create_and_validation(api_client, scheduling_api_setup):
    schedule = scheduling_api_setup["schedule"]
    alice = scheduling_api_setup["alice"]
    bob = scheduling_api_setup["bob"]
    charlie = scheduling_api_setup["charlie"]

    # 1. Ineligible user (Charlie belongs to other team)
    res_ineligible = api_client.post(
        "/api/schedule-rotations/",
        {
            "schedule": schedule.id,
            "user": charlie.id,
            "start_time": "2026-09-22T09:00:00Z",
            "end_time": "2026-09-22T17:00:00Z",
        },
        format="json",
    )
    assert res_ineligible.status_code == status.HTTP_400_BAD_REQUEST

    # 2. End time before start time
    res_range = api_client.post(
        "/api/schedule-rotations/",
        {
            "schedule": schedule.id,
            "user": alice.id,
            "start_time": "2026-09-22T17:00:00Z",
            "end_time": "2026-09-22T09:00:00Z",
        },
        format="json",
    )
    assert res_range.status_code == status.HTTP_400_BAD_REQUEST

    # 3. Base/base overlap rejection
    res_overlap = api_client.post(
        "/api/schedule-rotations/",
        {
            "schedule": schedule.id,
            "user": bob.id,
            "start_time": "2026-09-21T16:00:00Z",
            "end_time": "2026-09-21T20:00:00Z",
            "is_override": False,
        },
        format="json",
    )
    assert res_overlap.status_code == status.HTTP_400_BAD_REQUEST

    # 4. Valid new base rotation
    res_valid = api_client.post(
        "/api/schedule-rotations/",
        {
            "schedule": schedule.id,
            "user": bob.id,
            "start_time": "2026-09-21T17:00:00Z",
            "end_time": "2026-09-22T01:00:00Z",
            "is_override": False,
        },
        format="json",
    )
    assert res_valid.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_rotation_delete(api_client, scheduling_api_setup):
    rotation = scheduling_api_setup["rotation_override"]
    res = api_client.delete(f"/api/schedule-rotations/{rotation.id}/")
    assert res.status_code == status.HTTP_204_NO_CONTENT
    assert not ScheduleRotation.objects.filter(id=rotation.id).exists()


@pytest.mark.django_db
def test_on_call_endpoint(api_client, scheduling_api_setup):
    schedule = scheduling_api_setup["schedule"]
    alice = scheduling_api_setup["alice"]
    bob = scheduling_api_setup["bob"]

    # 1. Base window at 11:00 -> Alice
    res_1100 = api_client.get(f"/api/schedules/{schedule.id}/on-call/?at=2026-09-21T11:00:00Z")
    assert res_1100.status_code == status.HTTP_200_OK
    assert res_1100.data["user"]["id"] == alice.id
    assert res_1100.data["source"] == "base"

    # 2. Override window at 13:00 -> Bob
    res_1300 = api_client.get(f"/api/schedules/{schedule.id}/on-call/?at=2026-09-21T13:00:00Z")
    assert res_1300.status_code == status.HTTP_200_OK
    assert res_1300.data["user"]["id"] == bob.id
    assert res_1300.data["source"] == "override"

    # 3. Empty window at 03:00 -> user is null
    res_0300 = api_client.get(f"/api/schedules/{schedule.id}/on-call/?at=2026-09-21T03:00:00Z")
    assert res_0300.status_code == status.HTTP_200_OK
    assert res_0300.data["user"] is None
    assert res_0300.data["source"] is None

    # 4. Invalid timestamp -> 400 Bad Request
    res_invalid = api_client.get(f"/api/schedules/{schedule.id}/on-call/?at=invalid-time")
    assert res_invalid.status_code == status.HTTP_400_BAD_REQUEST

    # 5. Naive timestamp -> 400 Bad Request
    res_naive = api_client.get(f"/api/schedules/{schedule.id}/on-call/?at=2026-09-21T12:00:00")
    assert res_naive.status_code == status.HTTP_400_BAD_REQUEST
