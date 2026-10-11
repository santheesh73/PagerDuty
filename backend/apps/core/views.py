from typing import Any, cast

from django.db.models import QuerySet
from django.utils.cache import patch_cache_control
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response

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


def no_store(response: Response) -> Response:
    """Mark a response carrying a secret shown once (a key, a TOTP secret, backup codes).

    `no-store` keeps it out of browser and proxy caches, and the Idempotency-Key layer then keeps
    only a tombstone, so the secret is never written to Redis either.
    """
    patch_cache_control(response, no_store=True)
    return response
