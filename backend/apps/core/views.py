from typing import Any, cast

from django.db.models import QuerySet
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request

from apps.accounts.models import User

from .permissions import Role, has_role, member_team_ids


def actor(request: Request) -> User:
    """The authenticated user. Views behind IsAuthenticated can rely on this."""
    return cast(User, request.user)


def scope_to_teams(
    queryset: QuerySet[Any], user: Any, team_lookup: str = "team_id"
) -> QuerySet[Any]:
    """Restrict `queryset` to objects in `user`'s teams (staff see everything).

    Anonymous users get nothing, which also keeps OpenAPI schema generation quiet.
    """
    if not getattr(user, "is_authenticated", False):
        return queryset.none()
    if user.is_staff:
        return queryset
    return queryset.filter(**{f"{team_lookup}__in": member_team_ids(user)})


def require_role(user: Any, team_id: int | None, minimum: str) -> None:
    if not has_role(user, team_id, minimum):
        raise PermissionDenied(f"This needs the {Role(minimum).label.lower()} role on the team.")
