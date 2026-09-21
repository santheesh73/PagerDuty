from datetime import datetime, timezone as dt_timezone
import pytest

from apps.scheduling.models import Schedule, ScheduleRotation
from apps.scheduling.services import get_on_call, get_on_call_assignment
from apps.users.models import Team, TeamMembership, User


@pytest.fixture
def override_setup(db):
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

    # Base: Alice 09:00 - 17:00
    base_rot = ScheduleRotation.objects.create(
        schedule=schedule,
        user=alice,
        start_time=datetime(2026, 9, 21, 9, 0, 0, tzinfo=dt_timezone.utc),
        end_time=datetime(2026, 9, 21, 17, 0, 0, tzinfo=dt_timezone.utc),
        is_override=False,
    )

    # Override: Bob 12:00 - 14:00
    override_rot = ScheduleRotation.objects.create(
        schedule=schedule,
        user=bob,
        start_time=datetime(2026, 9, 21, 12, 0, 0, tzinfo=dt_timezone.utc),
        end_time=datetime(2026, 9, 21, 14, 0, 0, tzinfo=dt_timezone.utc),
        is_override=True,
    )

    return {
        "team": team,
        "alice": alice,
        "bob": bob,
        "schedule": schedule,
        "base_rot": base_rot,
        "override_rot": override_rot,
    }


@pytest.mark.django_db
def test_override_precedence_timeline(override_setup):
    """
    Mandatory Section 40 requirement:
    Base: Alice 09:00-17:00
    Override: Bob 12:00-14:00

    Expected:
    11:00 -> Alice
    12:00 -> Bob
    13:00 -> Bob
    14:00 -> Alice
    16:00 -> Alice
    """
    schedule = override_setup["schedule"]
    alice = override_setup["alice"]
    bob = override_setup["bob"]

    t_1100 = datetime(2026, 9, 21, 11, 0, 0, tzinfo=dt_timezone.utc)
    t_1200 = datetime(2026, 9, 21, 12, 0, 0, tzinfo=dt_timezone.utc)
    t_1300 = datetime(2026, 9, 21, 13, 0, 0, tzinfo=dt_timezone.utc)
    t_1400 = datetime(2026, 9, 21, 14, 0, 0, tzinfo=dt_timezone.utc)
    t_1600 = datetime(2026, 9, 21, 16, 0, 0, tzinfo=dt_timezone.utc)

    # 11:00 -> Alice (base)
    assert get_on_call(schedule, t_1100) == alice
    res_1100 = get_on_call_assignment(schedule, t_1100)
    assert res_1100["source"] == "base"
    assert res_1100["user"] == alice

    # 12:00 -> Bob (override begins)
    assert get_on_call(schedule, t_1200) == bob
    res_1200 = get_on_call_assignment(schedule, t_1200)
    assert res_1200["source"] == "override"
    assert res_1200["user"] == bob

    # 13:00 -> Bob (override mid)
    assert get_on_call(schedule, t_1300) == bob
    res_1300 = get_on_call_assignment(schedule, t_1300)
    assert res_1300["source"] == "override"
    assert res_1300["user"] == bob

    # 14:00 -> Alice (override ends, returns to base!)
    assert get_on_call(schedule, t_1400) == alice
    res_1400 = get_on_call_assignment(schedule, t_1400)
    assert res_1400["source"] == "base"
    assert res_1400["user"] == alice

    # 16:00 -> Alice (base)
    assert get_on_call(schedule, t_1600) == alice
    res_1600 = get_on_call_assignment(schedule, t_1600)
    assert res_1600["source"] == "base"
    assert res_1600["user"] == alice


@pytest.mark.django_db
def test_override_outside_base_rotation(db):
    team = Team.objects.create(name="Backend Team", slug="backend-team")
    bob = User.objects.create_user(username="bob")
    TeamMembership.objects.create(team=team, user=bob)

    schedule = Schedule.objects.create(
        name="Backend Primary",
        slug="backend-primary",
        team=team,
        timezone="UTC",
        is_primary=True,
        is_active=True,
    )

    # Standalone override with no base rotation
    ScheduleRotation.objects.create(
        schedule=schedule,
        user=bob,
        start_time=datetime(2026, 9, 21, 20, 0, 0, tzinfo=dt_timezone.utc),
        end_time=datetime(2026, 9, 21, 22, 0, 0, tzinfo=dt_timezone.utc),
        is_override=True,
    )

    assert get_on_call(schedule, datetime(2026, 9, 21, 21, 0, 0, tzinfo=dt_timezone.utc)) == bob
    assert get_on_call(schedule, datetime(2026, 9, 21, 19, 0, 0, tzinfo=dt_timezone.utc)) is None
