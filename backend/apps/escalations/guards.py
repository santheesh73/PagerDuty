"""Refuse to delete what an open incident's frozen policy still points at.

`EscalationTarget` already protects what the *live* policy references. An open incident however
escalates from its snapshot, taken when it opened, so a schedule or user that was edited out of
the policy since can still be named by it. Deleting that schedule or user would leave the incident
climbing through levels with nobody to page and nothing to say why. A `ProtectedError` becomes
HTTP 409 `in_use` through the API's exception handler.
"""

import functools
from typing import Any

from django.db.models import ProtectedError

from apps.accounts.models import User
from apps.incidents.models import Incident, Status
from apps.schedules.models import Schedule


def open_incidents_naming(kind: str, target_id: int):
    """Open incidents whose frozen policy has a `kind` target with this id."""
    return Incident.objects.exclude(status=Status.RESOLVED).filter(
        escalation_snapshot__rules__contains=[{"targets": [{"type": kind, "id": target_id}]}]
    )


def _refuse_if_named(kind: str, instance: Any) -> None:
    incidents = list(open_incidents_naming(kind, instance.pk)[:5])
    if incidents:
        numbers = ", ".join(f"#{i.number}" for i in incidents)
        raise ProtectedError(
            f"{kind} {instance.pk} is named by the frozen policy of open incident(s) {numbers}; "
            "resolve them first",
            set(incidents),
        )


def install() -> None:
    """Refuse a direct delete of a schedule or user that an open incident still names.

    Wraps `Model.delete`, which the API's DELETE, `obj.delete()` and the admin's single-object
    delete all call. Queryset and cascade deletes are deliberately *not* guarded: removing a team
    (which `seed_demo --reset` and a real team deletion do) deletes its services and incidents in
    the same cascade, so nothing is left behind to escalate to nobody. A `pre_delete` signal cannot
    tell those cases apart, and raising from it would also poison any enclosing transaction.
    """
    for model, kind in ((Schedule, "schedule"), (User, "user")):
        if getattr(model.delete, "_snapshot_guarded", False):
            continue
        original = model.delete

        @functools.wraps(original)
        def guarded(self: Any, *args: Any, _kind: str = kind, _orig: Any = original, **kw: Any):
            _refuse_if_named(_kind, self)
            return _orig(self, *args, **kw)

        guarded._snapshot_guarded = True  # type: ignore[attr-defined]
        model.delete = guarded  # type: ignore[method-assign]
