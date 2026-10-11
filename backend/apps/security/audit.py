"""Write an audit event. Never raises: a failure to audit must not fail the action it records
(it is logged instead, loudly)."""

import ipaddress
import logging
from typing import Any

from django.http import HttpRequest

from apps.core.logging import get_request_id
from apps.core.ratelimit import client_ident

from .models import AuditEvent

logger = logging.getLogger(__name__)


def record(
    action: str,
    *,
    request: HttpRequest | None = None,
    actor: Any = None,
    team_id: int | None = None,
    target: Any = None,
    **data: Any,
) -> None:
    if actor is None and request is not None:
        user = getattr(request, "user", None)
        actor = user if user is not None and user.is_authenticated else None
    try:
        AuditEvent.objects.create(
            action=action,
            actor_id=getattr(actor, "pk", None),
            actor_email=getattr(actor, "email", "") or "",
            team_id=team_id if team_id is not None else getattr(target, "team_id", None),
            target_type=type(target).__name__.lower() if target is not None else "",
            target_id=str(getattr(target, "pk", "") or ""),
            ip=_ip(request),
            request_id=get_request_id() or "",
            data=data,
        )
    except Exception:
        logger.exception("could not write audit event", extra={"action": action})


def _ip(request: HttpRequest | None) -> str | None:
    if request is None:
        return None
    try:
        return str(ipaddress.ip_address(client_ident(request)))
    except ValueError:
        return None


def _team_of(obj: Any) -> int | None:
    team = getattr(obj, "team_id", None)
    if team is None and getattr(obj, "schedule", None) is not None:
        team = obj.schedule.team_id
    return team


class AuditedMixin:
    """Records create/update/delete on a DRF viewset as `<audit_name>.<created|updated|deleted>`.

    Hooks `create`/`update`/`destroy` rather than `perform_*`, which the viewsets override for
    their own permission checks, so a subclass can never silently skip the record.
    """

    audit_name = ""

    def create(self, request: Any, *args: Any, **kwargs: Any) -> Any:
        response = super().create(request, *args, **kwargs)  # type: ignore[misc]
        obj = self.get_queryset().model.objects.filter(pk=response.data.get("id")).first()  # type: ignore[attr-defined]
        record(f"{self.audit_name}.created", request=request, target=obj, team_id=_team_of(obj))
        return response

    def update(self, request: Any, *args: Any, **kwargs: Any) -> Any:
        response = super().update(request, *args, **kwargs)  # type: ignore[misc]
        obj = self.get_object()  # type: ignore[attr-defined]
        record(
            f"{self.audit_name}.updated",
            request=request,
            target=obj,
            team_id=_team_of(obj),
            fields=sorted(map(str, request.data)) if hasattr(request.data, "keys") else [],
        )
        return response

    def destroy(self, request: Any, *args: Any, **kwargs: Any) -> Any:
        obj = self.get_object()  # type: ignore[attr-defined]
        team, pk, name = _team_of(obj), obj.pk, str(obj)
        response = super().destroy(request, *args, **kwargs)  # type: ignore[misc]
        record(
            f"{self.audit_name}.deleted",
            request=request,
            team_id=team,
            target_type=self.audit_name,
            deleted_id=pk,
            name=name,
        )
        return response
