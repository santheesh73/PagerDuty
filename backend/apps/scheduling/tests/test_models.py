from datetime import datetime, timedelta, timezone as dt_timezone
import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.scheduling.exceptions import IneligibleUserError, InvalidTimestampError, RotationOverlapError
from apps.scheduling.models import Schedule, ScheduleRotation
from apps.users.models import Team, TeamMembership, User


@pytest.mark.django_db
def test_schedule_belongs_to_team():
    team = Team.objects.create(name="Backend Team", slug="backend-team")
    schedule = Schedule.objects.create(
        name="Backend Primary",
        slug="backend-primary",
        team=team,
        timezone="UTC",
        is_primary=True,
        is_active=True,
    )
    assert schedule.team == team
    assert str(schedule) == "Backend Primary (Primary) [Backend Team]"


@pytest.mark.django_db
def test_unique_active_primary_schedule_per_team():
    team = Team.objects.create(name="Backend Team", slug="backend-team")
    Schedule.objects.create(
        name="Schedule 1",
        slug="schedule-1",
        team=team,
        timezone="UTC",
        is_primary=True,
        is_active=True,
    )

    with pytest.raises((IntegrityError, ValidationError)):
        Schedule.objects.create(
            name="Schedule 2",
            slug="schedule-2",
            team=team,
            timezone="UTC",
            is_primary=True,
            is_active=True,
        )


@pytest.mark.django_db
def test_multiple_non_primary_or_inactive_schedules_allowed():
    team = Team.objects.create(name="Backend Team", slug="backend-team")
    s1 = Schedule.objects.create(
        name="Schedule 1",
        slug="schedule-1",
        team=team,
        is_primary=True,
        is_active=True,
    )
    s2 = Schedule.objects.create(
        name="Schedule 2",
        slug="schedule-2",
        team=team,
        is_primary=False,
        is_active=True,
    )
    s3 = Schedule.objects.create(
        name="Schedule 3",
        slug="schedule-3",
        team=team,
        is_primary=True,
        is_active=False,
    )
    assert s1.id and s2.id and s3.id


@pytest.mark.django_db
def test_schedule_invalid_timezone_rejected():
    team = Team.objects.create(name="Backend Team", slug="backend-team")
    with pytest.raises(ValidationError):
        Schedule.objects.create(
            name="Invalid TZ Schedule",
            slug="invalid-tz",
            team=team,
            timezone="Invalid/Timezone",
        )


@pytest.mark.django_db
def test_schedule_cannot_be_active_on_inactive_team():
    team = Team.objects.create(name="Inactive Team", slug="inactive-team", is_active=False)
    with pytest.raises(ValidationError):
        Schedule.objects.create(
            name="Schedule Inactive Team",
            slug="sched-inactive-team",
            team=team,
            is_active=True,
        )


@pytest.mark.django_db
def test_rotation_end_time_must_be_after_start_time():
    team = Team.objects.create(name="Backend Team", slug="backend-team")
    user = User.objects.create_user(username="alice")
    TeamMembership.objects.create(team=team, user=user)
    schedule = Schedule.objects.create(name="Sched", slug="sched", team=team)

    t = datetime(2026, 9, 21, 10, 0, tzinfo=dt_timezone.utc)
    with pytest.raises((ValidationError, IntegrityError)):
        ScheduleRotation.objects.create(
            schedule=schedule,
            user=user,
            start_time=t,
            end_time=t,
        )


@pytest.mark.django_db
def test_rotation_naive_datetime_rejected():
    team = Team.objects.create(name="Backend Team", slug="backend-team")
    user = User.objects.create_user(username="alice")
    TeamMembership.objects.create(team=team, user=user)
    schedule = Schedule.objects.create(name="Sched", slug="sched", team=team)

    t1 = datetime(2026, 9, 21, 10, 0)
    t2 = datetime(2026, 9, 21, 12, 0)
    with pytest.raises((InvalidTimestampError, ValidationError)):
        ScheduleRotation.objects.create(
            schedule=schedule,
            user=user,
            start_time=t1,
            end_time=t2,
        )


@pytest.mark.django_db
def test_rotation_inactive_user_rejected():
    team = Team.objects.create(name="Backend Team", slug="backend-team")
    user = User.objects.create_user(username="alice", is_active=False)
    TeamMembership.objects.create(team=team, user=user)
    schedule = Schedule.objects.create(name="Sched", slug="sched", team=team)

    t1 = datetime(2026, 9, 21, 10, 0, tzinfo=dt_timezone.utc)
    t2 = datetime(2026, 9, 21, 12, 0, tzinfo=dt_timezone.utc)
    with pytest.raises(IneligibleUserError):
        ScheduleRotation.objects.create(
            schedule=schedule,
            user=user,
            start_time=t1,
            end_time=t2,
        )


@pytest.mark.django_db
def test_rotation_non_team_member_user_rejected():
    team1 = Team.objects.create(name="Backend Team", slug="backend-team")
    team2 = Team.objects.create(name="SRE Team", slug="sre-team")
    user = User.objects.create_user(username="charlie")
    TeamMembership.objects.create(team=team2, user=user)
    schedule = Schedule.objects.create(name="Backend Primary", slug="backend-primary", team=team1)

    t1 = datetime(2026, 9, 21, 10, 0, tzinfo=dt_timezone.utc)
    t2 = datetime(2026, 9, 21, 12, 0, tzinfo=dt_timezone.utc)
    with pytest.raises(IneligibleUserError):
        ScheduleRotation.objects.create(
            schedule=schedule,
            user=user,
            start_time=t1,
            end_time=t2,
        )


@pytest.mark.django_db
def test_rotation_inactive_membership_rejected():
    team = Team.objects.create(name="Backend Team", slug="backend-team")
    user = User.objects.create_user(username="alice")
    TeamMembership.objects.create(team=team, user=user, is_active=False)
    schedule = Schedule.objects.create(name="Sched", slug="sched", team=team)

    t1 = datetime(2026, 9, 21, 10, 0, tzinfo=dt_timezone.utc)
    t2 = datetime(2026, 9, 21, 12, 0, tzinfo=dt_timezone.utc)
    with pytest.raises(IneligibleUserError):
        ScheduleRotation.objects.create(
            schedule=schedule,
            user=user,
            start_time=t1,
            end_time=t2,
        )


@pytest.mark.django_db
def test_base_rotations_overlap_rejected():
    team = Team.objects.create(name="Backend Team", slug="backend-team")
    alice = User.objects.create_user(username="alice")
    bob = User.objects.create_user(username="bob")
    TeamMembership.objects.create(team=team, user=alice)
    TeamMembership.objects.create(team=team, user=bob)
    schedule = Schedule.objects.create(name="Sched", slug="sched", team=team)

    # Alice: 09:00 - 17:00
    ScheduleRotation.objects.create(
        schedule=schedule,
        user=alice,
        start_time=datetime(2026, 9, 21, 9, 0, tzinfo=dt_timezone.utc),
        end_time=datetime(2026, 9, 21, 17, 0, tzinfo=dt_timezone.utc),
        is_override=False,
    )

    # Bob: 16:00 - 20:00 (overlaps with Alice)
    with pytest.raises(RotationOverlapError):
        ScheduleRotation.objects.create(
            schedule=schedule,
            user=bob,
            start_time=datetime(2026, 9, 21, 16, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2026, 9, 21, 20, 0, tzinfo=dt_timezone.utc),
            is_override=False,
        )


@pytest.mark.django_db
def test_override_rotations_overlap_rejected():
    team = Team.objects.create(name="Backend Team", slug="backend-team")
    alice = User.objects.create_user(username="alice")
    bob = User.objects.create_user(username="bob")
    TeamMembership.objects.create(team=team, user=alice)
    TeamMembership.objects.create(team=team, user=bob)
    schedule = Schedule.objects.create(name="Sched", slug="sched", team=team)

    ScheduleRotation.objects.create(
        schedule=schedule,
        user=alice,
        start_time=datetime(2026, 9, 21, 12, 0, tzinfo=dt_timezone.utc),
        end_time=datetime(2026, 9, 21, 14, 0, tzinfo=dt_timezone.utc),
        is_override=True,
    )

    with pytest.raises(RotationOverlapError):
        ScheduleRotation.objects.create(
            schedule=schedule,
            user=bob,
            start_time=datetime(2026, 9, 21, 13, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2026, 9, 21, 15, 0, tzinfo=dt_timezone.utc),
            is_override=True,
        )


@pytest.mark.django_db
def test_override_overlapping_base_allowed():
    team = Team.objects.create(name="Backend Team", slug="backend-team")
    alice = User.objects.create_user(username="alice")
    bob = User.objects.create_user(username="bob")
    TeamMembership.objects.create(team=team, user=alice)
    TeamMembership.objects.create(team=team, user=bob)
    schedule = Schedule.objects.create(name="Sched", slug="sched", team=team)

    # Base: Alice 09:00 - 17:00
    base = ScheduleRotation.objects.create(
        schedule=schedule,
        user=alice,
        start_time=datetime(2026, 9, 21, 9, 0, tzinfo=dt_timezone.utc),
        end_time=datetime(2026, 9, 21, 17, 0, tzinfo=dt_timezone.utc),
        is_override=False,
    )

    # Override: Bob 12:00 - 14:00 (overlaps Base)
    override = ScheduleRotation.objects.create(
        schedule=schedule,
        user=bob,
        start_time=datetime(2026, 9, 21, 12, 0, tzinfo=dt_timezone.utc),
        end_time=datetime(2026, 9, 21, 14, 0, tzinfo=dt_timezone.utc),
        is_override=True,
    )

    assert base.id is not None
    assert override.id is not None


@pytest.mark.django_db
def test_adjacent_rotations_allowed():
    team = Team.objects.create(name="Backend Team", slug="backend-team")
    alice = User.objects.create_user(username="alice")
    bob = User.objects.create_user(username="bob")
    TeamMembership.objects.create(team=team, user=alice)
    TeamMembership.objects.create(team=team, user=bob)
    schedule = Schedule.objects.create(name="Sched", slug="sched", team=team)

    r1 = ScheduleRotation.objects.create(
        schedule=schedule,
        user=alice,
        start_time=datetime(2026, 9, 21, 9, 0, tzinfo=dt_timezone.utc),
        end_time=datetime(2026, 9, 21, 17, 0, tzinfo=dt_timezone.utc),
        is_override=False,
    )
    r2 = ScheduleRotation.objects.create(
        schedule=schedule,
        user=bob,
        start_time=datetime(2026, 9, 21, 17, 0, tzinfo=dt_timezone.utc),
        end_time=datetime(2026, 9, 22, 1, 0, tzinfo=dt_timezone.utc),
        is_override=False,
    )
    assert r1.id and r2.id
