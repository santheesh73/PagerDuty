from datetime import datetime
from typing import Any

from django.db.models import Q, QuerySet

from apps.accounts.models import User
from apps.core.permissions import member_team_ids

from .models import Incident, IncidentEvent


def visible_incidents(user: Any) -> QuerySet[Incident]:
    incidents = Incident.objects.select_related("service", "assignee")
    if not getattr(user, "is_authenticated", False):
        return incidents.none()
    if user.is_staff:
        return incidents
    return incidents.filter(service__team_id__in=member_team_ids(user))


def filter_incidents(
    incidents: QuerySet[Incident],
    *,
    user: User,
    status: list[str] | None = None,
    urgency: str | None = None,
    service: int | None = None,
    team: int | None = None,
    assignee: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    search: str | None = None,
) -> QuerySet[Incident]:
    if status:
        incidents = incidents.filter(status__in=status)
    if urgency:
        incidents = incidents.filter(urgency=urgency)
    if service:
        incidents = incidents.filter(service_id=service)
    if team:
        incidents = incidents.filter(service__team_id=team)
    if assignee == "me":
        incidents = incidents.filter(assignee=user)
    elif assignee and assignee.isdigit():
        incidents = incidents.filter(assignee_id=int(assignee))
    if since:
        incidents = incidents.filter(triggered_at__gte=since)
    if until:
        incidents = incidents.filter(triggered_at__lt=until)
    if search := (search or "").strip():
        query = Q(title__icontains=search) | Q(dedup_key__iexact=search)
        if search.lstrip("#").isdigit():
            query |= Q(number=int(search.lstrip("#")))
        incidents = incidents.filter(query)
    return incidents


def timeline(incident: Incident) -> QuerySet[IncidentEvent]:
    return incident.events.select_related("actor")


def snapshot_with_names(incident: Incident) -> dict[str, Any]:
    """The frozen snapshot, decorated with display names for the UI."""
    from apps.schedules.models import Schedule

    snapshot = incident.escalation_snapshot or {}
    rules = snapshot.get("rules") or []
    user_ids = {t["id"] for r in rules for t in r["targets"] if t["type"] == "user"}
    schedule_ids = {t["id"] for r in rules for t in r["targets"] if t["type"] == "schedule"}
    users = dict(User.objects.filter(pk__in=user_ids).values_list("pk", "name"))
    schedules = dict(Schedule.objects.filter(pk__in=schedule_ids).values_list("pk", "name"))
    return {
        **snapshot,
        "rules": [
            {
                **rule,
                "targets": [
                    {
                        **t,
                        "name": (users if t["type"] == "user" else schedules).get(
                            t["id"], "(deleted)"
                        ),
                    }
                    for t in rule["targets"]
                ],
            }
            for rule in rules
        ],
    }
