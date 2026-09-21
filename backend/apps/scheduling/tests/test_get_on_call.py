from datetime import datetime, timezone as dt_timezone
import pytest

from apps.scheduling.exceptions import InvalidTimestampError
from apps.scheduling.models import Schedule, ScheduleRotation
from apps.scheduling.services import get_current_on_call, get_on_call, get_on_call_assignment
from apps.users.models import Team, TeamMembership, User


@pytest.fixture
def on_call_setup(db):
    team = Team.objects.create(name="Backend Team", slug="backend-team")
    alice = User.objects.create_user(username="alice")
    bob = User.objects.create_user(username="bob")
    TeamMembership.objects.create(team=team, user=alice)
    TeamMembership.objects.create(team=team, user=bob)

    schedule = Schedule.objects.create(
        name="Backend Primary",
        slug="backend-primary",
        team=team,
        timezone="UTC",
        is_primary=True,
        is_active=True,
    )

    # Alice: 09:00 <= t < 17:00
    r1 = ScheduleRotation.objects.create(
        schedule=schedule,
        user=alice,
        start_time=datetime(2026, 9, 21, 9, 0, 0, tzinfo=dt_timezone.utc),
        end_time=datetime(2026, 9, 21, 17, 0, 0, tzinfo=dt_timezone.utc),
        is_override=False,
    )

    # Bob: 17:00 <= t < 01:00 (next day)
    r2 = ScheduleRotation.objects.create(
        schedule=schedule,
        user=bob,
        start_time=datetime(2026, 9, 21, 17, 0, 0, tzinfo=dt_timezone.utc),
        end_time=datetime(2026, 9, 22, 1, 0, 0, tzinfo=dt_timezone.utc),
        is_override=False,
    )

    return {
        "team": team,
        "alice": alice,
        "bob": bob,
        "schedule": schedule,
        "rotation_alice": r1,
        "rotation_bob": r2,
    }


@pytest.mark.django_db
def test_get_on_call_base_rotation_boundaries(on_call_setup):
    schedule = on_call_setup["schedule"]
    alice = on_call_setup["alice"]
    bob = on_call_setup["bob"]

    # At exact start: 09:00:00 -> Alice
    assert get_on_call(schedule, datetime(2026, 9, 21, 9, 0, 0, tzinfo=dt_timezone.utc)) == alice

    # Mid shift: 12:00:00 -> Alice
    assert get_on_call(schedule, datetime(2026, 9, 21, 12, 0, 0, tzinfo=dt_timezone.utc)) == alice

    # One second before end: 16:59:59 -> Alice
    assert get_on_call(schedule, datetime(2026, 9, 21, 16, 59, 59, tzinfo=dt_timezone.utc)) == alice

    # At exact handoff: 17:00:00 -> NOT Alice, but Bob!
    at_1700 = get_on_call(schedule, datetime(2026, 9, 21, 17, 0, 0, tzinfo=dt_timezone.utc))
    assert at_1700 != alice
    assert at_1700 == bob

    # Later in Bob shift: 20:00:00 -> Bob
    assert get_on_call(schedule, datetime(2026, 9, 21, 20, 0, 0, tzinfo=dt_timezone.utc)) == bob


@pytest.mark.django_db
def test_get_on_call_outside_rotation_windows(on_call_setup):
    schedule = on_call_setup["schedule"]

    # Before first rotation: 08:59:59 -> None
    assert get_on_call(schedule, datetime(2026, 9, 21, 8, 59, 59, tzinfo=dt_timezone.utc)) is None

    # After last rotation: 01:00:00 next day -> None
    assert get_on_call(schedule, datetime(2026, 9, 22, 1, 0, 0, tzinfo=dt_timezone.utc)) is None


@pytest.mark.django_db
def test_get_on_call_naive_timestamp_rejected(on_call_setup):
    schedule = on_call_setup["schedule"]
    naive_ts = datetime(2026, 9, 21, 12, 0, 0)

    with pytest.raises(InvalidTimestampError):
        get_on_call(schedule, naive_ts)

    with pytest.raises(InvalidTimestampError):
        get_on_call_assignment(schedule, naive_ts)


@pytest.mark.django_db
def test_get_on_call_inactive_schedule(on_call_setup):
    schedule = on_call_setup["schedule"]
    schedule.is_active = False
    schedule.save()

    # Active rotation exists, but schedule itself is inactive
    result = get_on_call(schedule, datetime(2026, 9, 21, 12, 0, 0, tzinfo=dt_timezone.utc))
    assert result is None


@pytest.mark.django_db
def test_get_on_call_assignment_metadata(on_call_setup):
    schedule = on_call_setup["schedule"]
    alice = on_call_setup["alice"]

    assignment = get_on_call_assignment(schedule, datetime(2026, 9, 21, 10, 0, 0, tzinfo=dt_timezone.utc))
    assert assignment is not None
    assert assignment["user"] == alice
    assert assignment["source"] == "base"
    assert assignment["rotation"].id == on_call_setup["rotation_alice"].id


@pytest.mark.django_db
def test_get_current_on_call(on_call_setup):
    schedule = on_call_setup["schedule"]
    # Convenience function does not raise
    user = get_current_on_call(schedule)
    assert user is None or user in (on_call_setup["alice"], on_call_setup["bob"])
