import pytest
from django.db import IntegrityError

from apps.users.models import Team, TeamMembership, User


@pytest.mark.django_db
def test_create_valid_user():
    """Verify creation and string representation of a custom User."""
    user = User.objects.create_user(
        username="alice",
        email="alice@example.com",
        first_name="Alice",
        last_name="Smith",
    )
    assert user.id is not None
    assert user.username == "alice"
    assert user.is_active is True
    assert str(user) == "Alice Smith"


@pytest.mark.django_db
def test_user_inactive_state():
    """Verify inactive state flag on User."""
    user = User.objects.create_user(username="inactive_user", is_active=False)
    assert user.is_active is False


@pytest.mark.django_db
def test_create_valid_team():
    """Verify creation, slug, and string representation of a Team."""
    team = Team.objects.create(
        name="Backend Team",
        slug="backend",
        description="Handles core backend services",
    )
    assert team.id is not None
    assert team.is_active is True
    assert str(team) == "Backend Team"


@pytest.mark.django_db
def test_team_slug_uniqueness():
    """Verify that duplicate team slugs are rejected by database constraint."""
    Team.objects.create(name="Team A", slug="alpha")
    with pytest.raises(IntegrityError):
        Team.objects.create(name="Team B", slug="alpha")


@pytest.mark.django_db
def test_create_valid_team_membership():
    """Verify creation of a valid TeamMembership with default role."""
    user = User.objects.create_user(username="alice")
    team = Team.objects.create(name="Backend Team", slug="backend")

    membership = TeamMembership.objects.create(
        user=user,
        team=team,
        role=TeamMembership.Role.ENGINEER,
    )
    assert membership.id is not None
    assert membership.is_active is True
    assert membership.role == TeamMembership.Role.ENGINEER
    assert "alice" in str(membership)
    assert "Backend Team" in str(membership)


@pytest.mark.django_db
def test_duplicate_user_team_membership_rejected_by_db():
    """Verify that database constraint prevents duplicate memberships for same user and team."""
    user = User.objects.create_user(username="alice")
    team = Team.objects.create(name="Backend Team", slug="backend")

    TeamMembership.objects.create(user=user, team=team, role=TeamMembership.Role.ENGINEER)

    with pytest.raises(IntegrityError):
        TeamMembership.objects.create(user=user, team=team, role=TeamMembership.Role.LEAD)


@pytest.mark.django_db
def test_membership_active_inactive_toggle():
    """Verify that membership can be deactivated without deleting the record."""
    user = User.objects.create_user(username="alice")
    team = Team.objects.create(name="Backend Team", slug="backend")

    membership = TeamMembership.objects.create(user=user, team=team)
    assert membership.is_active is True

    membership.is_active = False
    membership.save()
    membership.refresh_from_db()
    assert membership.is_active is False
