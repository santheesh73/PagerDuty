from django.core.exceptions import ValidationError

from .models import Team, TeamMembership, User


def add_user_to_team(
    user: User,
    team: Team,
    role: str = TeamMembership.Role.ENGINEER,
    is_active: bool = True,
) -> TeamMembership:
    """
    Centralized domain service to add a user to a team.
    Enforces active user/team rules, role validity, and handles reactivation
    if a deactivated membership record already exists.
    """
    if role not in TeamMembership.Role.values:
        valid_roles = ", ".join(TeamMembership.Role.values)
        raise ValidationError(f"Invalid role '{role}'. Must be one of: {valid_roles}.")

    if is_active:
        if not user.is_active:
            raise ValidationError("Cannot add an inactive user to a team.")
        if not team.is_active:
            raise ValidationError("Cannot add a user to an inactive team.")

    membership = TeamMembership.objects.filter(user=user, team=team).first()

    if membership:
        if membership.is_active and is_active:
            raise ValidationError("User is already an active member of this team.")
        # Reactivate or update existing membership
        membership.role = role
        membership.is_active = is_active
        membership.save(update_fields=["role", "is_active", "updated_at"])
        return membership

    return TeamMembership.objects.create(
        user=user,
        team=team,
        role=role,
        is_active=is_active,
    )


def remove_user_from_team(user: User, team: Team, soft: bool = True) -> TeamMembership | None:
    """
    Removes a user from a team.
    Defaults to soft-deactivation (is_active = False) to preserve audit trails.
    """
    membership = TeamMembership.objects.filter(user=user, team=team).first()
    if not membership:
        return None

    if soft:
        membership.is_active = False
        membership.save(update_fields=["is_active", "updated_at"])
        return membership

    membership.delete()
    return None
