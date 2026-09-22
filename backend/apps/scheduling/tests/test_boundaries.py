from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ValidationError

from apps.incidents.models import Incident
from apps.scheduling.models import Schedule, ScheduleRotation
from apps.scheduling.services import get_on_call
from apps.services.models import Service
from apps.users.models import Team, TeamMembership, User


@pytest.fixture
def boundary_setup(db):
    team = Team.objects.create(name="Boundary Team", slug="boundary-team")
    alice = User.objects.create_user(username="bnd_alice", email="alice@example.com")
    bob = User.objects.create_user(username="bnd_bob", email="bob@example.com")
    TeamMembership.objects.create(team=team, user=alice, role=TeamMembership.Role.RESPONDER, is_active=True)
    TeamMembership.objects.create(team=team, user=bob, role=TeamMembership.Role.RESPONDER, is_active=True)

    schedule = Schedule.objects.create(
        name="Boundary Schedule",
        slug="boundary-sched",
        team=team,
        timezone="UTC",
        is_primary=True,
        is_active=True,
    )
    return {
        "team": team,
        "alice": alice,
        "bob": bob,
        "schedule": schedule,
    }


@pytest.mark.django_db
def test_subsecond_exact_boundary_resolution(boundary_setup):
    """
    Section 22: Schedule Boundary Precision (Sub-second / Microsecond resolution).
    Alice: 09:00 <= t < 17:00 UTC
    Bob:   17:00 <= t < 23:00 UTC

    Verify:
    - 08:59:59.999999 -> None
    - 09:00:00.000000 -> Alice
    - 16:59:59.999999 -> Alice
    - 17:00:00.000000 -> Bob
    - 22:59:59.999999 -> Bob
    - 23:00:00.000000 -> None
    """
    sched = boundary_setup["schedule"]
    alice = boundary_setup["alice"]
    bob = boundary_setup["bob"]

    ScheduleRotation.objects.create(
        schedule=sched,
        user=alice,
        start_time=datetime(2026, 9, 22, 9, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 9, 22, 17, 0, 0, tzinfo=UTC),
    )
    ScheduleRotation.objects.create(
        schedule=sched,
        user=bob,
        start_time=datetime(2026, 9, 22, 17, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 9, 22, 23, 0, 0, tzinfo=UTC),
    )

    t_before_alice = datetime(2026, 9, 22, 8, 59, 59, 999999, tzinfo=UTC)
    t_start_alice = datetime(2026, 9, 22, 9, 0, 0, 0, tzinfo=UTC)
    t_end_alice_sub = datetime(2026, 9, 22, 16, 59, 59, 999999, tzinfo=UTC)
    t_start_bob = datetime(2026, 9, 22, 17, 0, 0, 0, tzinfo=UTC)
    t_end_bob_sub = datetime(2026, 9, 22, 22, 59, 59, 999999, tzinfo=UTC)
    t_after_bob = datetime(2026, 9, 22, 23, 0, 0, 0, tzinfo=UTC)

    assert get_on_call(sched, t_before_alice) is None
    assert get_on_call(sched, t_start_alice) == alice
    assert get_on_call(sched, t_end_alice_sub) == alice
    assert get_on_call(sched, t_start_bob) == bob
    assert get_on_call(sched, t_end_bob_sub) == bob
    assert get_on_call(sched, t_after_bob) is None


@pytest.mark.django_db
def test_midnight_crossing_rotation(boundary_setup):
    """
    Section 23: Midnight Crossing.
    Shift crosses calendar date: 2026-09-22 17:00 UTC to 2026-09-23 01:00 UTC.
    Expected:
    - 2026-09-22 16:59:59 -> None
    - 2026-09-22 17:00:00 -> Alice
    - 2026-09-23 00:00:00 (Midnight) -> Alice
    - 2026-09-23 00:59:59 -> Alice
    - 2026-09-23 01:00:00 -> None
    """
    sched = boundary_setup["schedule"]
    alice = boundary_setup["alice"]

    ScheduleRotation.objects.create(
        schedule=sched,
        user=alice,
        start_time=datetime(2026, 9, 22, 17, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 9, 23, 1, 0, 0, tzinfo=UTC),
    )

    t_before = datetime(2026, 9, 22, 16, 59, 59, tzinfo=UTC)
    t_start = datetime(2026, 9, 22, 17, 0, 0, tzinfo=UTC)
    t_midnight = datetime(2026, 9, 23, 0, 0, 0, tzinfo=UTC)
    t_pre_end = datetime(2026, 9, 23, 0, 59, 59, tzinfo=UTC)
    t_end = datetime(2026, 9, 23, 1, 0, 0, tzinfo=UTC)

    assert get_on_call(sched, t_before) is None
    assert get_on_call(sched, t_start) == alice
    assert get_on_call(sched, t_midnight) == alice
    assert get_on_call(sched, t_pre_end) == alice
    assert get_on_call(sched, t_end) is None


@pytest.mark.django_db
def test_dst_transition_america_new_york(boundary_setup):
    """
    Section 25: DST Hardening.
    Schedule configured in America/New_York.
    Spring forward: 2026-03-08 (at 02:00 EST -> 03:00 EDT).
    Fall back: 2026-11-01 (at 02:00 EDT -> 01:00 EST).
    All database storage remains strictly UTC aware.
    Assert correct resolution across the DST boundary without timezone ambiguity.
    """
    team = boundary_setup["team"]
    alice = boundary_setup["alice"]

    ny_sched = Schedule.objects.create(
        name="NY Schedule",
        slug="ny-sched",
        team=team,
        timezone="America/New_York",
        is_primary=False,
        is_active=True,
    )

    # Shift spanning across spring-forward transition (stored in UTC):
    # 2026-03-08 05:00 UTC (00:00 EST) to 2026-03-08 15:00 UTC (11:00 EDT)
    start_utc = datetime(2026, 3, 8, 5, 0, 0, tzinfo=UTC)
    end_utc = datetime(2026, 3, 8, 15, 0, 0, tzinfo=UTC)

    ScheduleRotation.objects.create(
        schedule=ny_sched,
        user=alice,
        start_time=start_utc,
        end_time=end_utc,
    )

    # Test before shift in local NY time
    ny_tz = ZoneInfo("America/New_York")
    t_pre = datetime(2026, 3, 7, 23, 59, 0, tzinfo=ny_tz)
    assert get_on_call(ny_sched, t_pre) is None

    # Test during shift across the transition
    t_during = datetime(2026, 3, 8, 4, 30, 0, tzinfo=ny_tz)  # 04:30 EDT is 08:30 UTC
    assert get_on_call(ny_sched, t_during) == alice

    # Test after shift
    t_post = datetime(2026, 3, 8, 12, 0, 0, tzinfo=ny_tz)  # 12:00 EDT is 16:00 UTC
    assert get_on_call(ny_sched, t_post) is None


@pytest.mark.django_db
def test_schedule_and_user_deactivation_preserves_historical_incident_assignment(boundary_setup):
    """
    Section 28 & 29: Schedule Change & User Deactivation During Active Incident.
    When an incident is assigned to Alice, and subsequently:
    - Alice is deactivated (is_active = False)
    - Schedule is deactivated (is_active = False)
    The existing Incident must retain Alice as assigned_user (audit preservation).
    """
    team = boundary_setup["team"]
    alice = boundary_setup["alice"]
    sched = boundary_setup["schedule"]

    service = Service.objects.create(name="Preserve Svc", slug="preserve-svc", team=team)
    incident = Incident.objects.create(
        service=service,
        title="Historical preservation test",
        severity=Incident.Severity.CRITICAL,
        fingerprint="preserve_fp",
        status=Incident.Status.TRIGGERED,
        assigned_user=alice,
    )

    # Deactivate schedule
    sched.is_active = False
    sched.save(update_fields=["is_active"])

    # Deactivate user
    alice.is_active = False
    alice.save(update_fields=["is_active"])

    # Historical assignment on existing incident remains untouched
    incident.refresh_from_db()
    assert incident.assigned_user == alice
    assert incident.assigned_user.is_active is False


@pytest.mark.django_db
def test_concurrent_or_overlapping_overrides_rejected(boundary_setup):
    """
    Section 27: Multiple Invalid Overrides.
    Two overlapping overrides for the same schedule must be rejected by clean() validation.
    """
    sched = boundary_setup["schedule"]
    alice = boundary_setup["alice"]
    bob = boundary_setup["bob"]

    ScheduleRotation.objects.create(
        schedule=sched,
        user=alice,
        start_time=datetime(2026, 9, 22, 12, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 9, 22, 14, 0, 0, tzinfo=UTC),
        is_override=True,
    )

    # Attempt overlapping override (13:00 - 15:00)
    overlapping_override = ScheduleRotation(
        schedule=sched,
        user=bob,
        start_time=datetime(2026, 9, 22, 13, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 9, 22, 15, 0, 0, tzinfo=UTC),
        is_override=True,
    )

    with pytest.raises(ValidationError):
        overlapping_override.full_clean()
