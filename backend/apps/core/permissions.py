"""Every authorization rule in one file.

Model: one org, many teams. A user's power over an object comes from their Membership
in the object's team:
  viewer    → read
  responder → read + act on incidents (ack, resolve, notes, ...)
  admin     → all of the above + edit the team's services, policies and schedules
Staff users (Django admin) are treated as admins of every team.
"""

from typing import Any

from django.db.models import Model
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.accounts.models import Membership

Role = Membership.Role
_RANK = {Role.VIEWER: 0, Role.RESPONDER: 1, Role.ADMIN: 2}


def team_id_of(obj: Model) -> int | None:
    """Walk from any domain object to its owning team id."""
    for path in (
        "team_id",
        "service.team_id",
        "schedule.team_id",
        "policy.team_id",
        "incident.service.team_id",
    ):
        current: Any = obj
        for attr in path.split("."):
            current = getattr(current, attr, None)
            if current is None:
                break
        if current is not None:
            return int(current)
    return None


def role_in_team(user: Any, team_id: int | None) -> str | None:
    if not user or not user.is_authenticated or team_id is None:
        return None
    if user.is_staff:
        return Role.ADMIN
    cache = getattr(user, "_pulse_roles", None)
    if cache is None:
        cache = dict(Membership.objects.filter(user=user).values_list("team_id", "role"))
        user._pulse_roles = cache  # per-request memo: the user object lives for one request
    return cache.get(team_id)


def has_role(user: Any, team_id: int | None, minimum: str) -> bool:
    role = role_in_team(user, team_id)
    return role is not None and _RANK[Role(role)] >= _RANK[Role(minimum)]


def member_team_ids(user: Any) -> set[int]:
    return set(Membership.objects.filter(user=user).values_list("team_id", flat=True))


def admin_team_ids(user: Any) -> set[int]:
    if user.is_staff:
        from apps.accounts.models import Team

        return set(Team.objects.values_list("id", flat=True))
    return set(
        Membership.objects.filter(user=user, role=Role.ADMIN).values_list("team_id", flat=True)
    )


class _Authenticated(BasePermission):
    """Setting `permission_classes` replaces DRF's default IsAuthenticated, so every class
    here re-asserts it. Without this, list endpoints would be open to anonymous users."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(request.user and request.user.is_authenticated)


class IsTeamMember(_Authenticated):
    """Read for any member of the object's team; writes need admin (config objects)."""

    def has_object_permission(self, request: Request, view: APIView, obj: Model) -> bool:
        team_id = team_id_of(obj)
        if request.method in SAFE_METHODS:
            return has_role(request.user, team_id, Role.VIEWER)
        return has_role(request.user, team_id, Role.ADMIN)


class CanRespond(_Authenticated):
    """Read for members; incident actions for responders and admins."""

    def has_object_permission(self, request: Request, view: APIView, obj: Model) -> bool:
        team_id = team_id_of(obj)
        if request.method in SAFE_METHODS:
            return has_role(request.user, team_id, Role.VIEWER)
        return has_role(request.user, team_id, Role.RESPONDER)
