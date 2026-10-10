"""Response metrics, computed on read with ORM aggregates — no rollup tables to keep in sync.

The `(service, triggered_at)` index serves every query here. Maintenance incidents are
excluded everywhere: they never page, so they'd only flatter the response times.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q, QuerySet, Sum
from django.db.models.functions import TruncDate

from apps.accounts.models import User
from apps.core.permissions import member_team_ids
from apps.incidents.models import EventType, Incident, Urgency


@dataclass(frozen=True)
class Window:
    since: datetime
    until: datetime
    service: int | None = None
    team: int | None = None


def _elapsed(field: str) -> ExpressionWrapper:
    return ExpressionWrapper(F(field) - F("triggered_at"), output_field=DurationField())


def _seconds(value: timedelta | None) -> float | None:
    return round(value.total_seconds(), 1) if value is not None else None


def incidents_in(user: User, window: Window) -> QuerySet[Incident]:
    incidents = Incident.objects.filter(
        is_maintenance=False, triggered_at__gte=window.since, triggered_at__lt=window.until
    )
    if not user.is_staff:
        incidents = incidents.filter(service__team_id__in=member_team_ids(user))
    if window.service:
        incidents = incidents.filter(service_id=window.service)
    if window.team:
        incidents = incidents.filter(service__team_id=window.team)
    return incidents


def _response_times(incidents: QuerySet[Incident]) -> dict[str, Any]:
    return incidents.aggregate(
        incidents=Count("pk"),
        high=Count("pk", filter=Q(urgency=Urgency.HIGH)),
        low=Count("pk", filter=Q(urgency=Urgency.LOW)),
        time_to_first_response=Avg(
            _elapsed("first_response_at"), filter=Q(first_response_at__isnull=False)
        ),
        mtta=Avg(_elapsed("acknowledged_at"), filter=Q(acknowledged_at__isnull=False)),
        mttr=Avg(_elapsed("resolved_at"), filter=Q(resolved_at__isnull=False)),
    )


def summary(user: User, window: Window) -> dict[str, Any]:
    incidents = incidents_in(user, window)
    totals = _response_times(incidents)
    # Separate query on purpose: joining events into the aggregate above would multiply
    # rows and skew every average.
    escalated = incidents.filter(events__type=EventType.ESCALATED).distinct().count()
    noisy = (
        incidents.values("service_id", "service__name")
        .annotate(alert_total=Sum("alert_count"), incident_count=Count("pk"))
        .order_by("-alert_total", "service__name")[:5]
    )
    count = totals["incidents"]
    return {
        "since": window.since,
        "until": window.until,
        "incidents": count,
        "by_urgency": {"high": totals["high"], "low": totals["low"]},
        "time_to_first_response_seconds": _seconds(totals["time_to_first_response"]),
        "mtta_seconds": _seconds(totals["mtta"]),
        "mttr_seconds": _seconds(totals["mttr"]),
        "escalation_rate": round(escalated / count, 4) if count else None,
        "noisy_services": [
            {
                "id": row["service_id"],
                "name": row["service__name"],
                "alerts": row["alert_total"],
                "incidents": row["incident_count"],
            }
            for row in noisy
        ],
    }


def timeseries(user: User, window: Window, tz: str) -> list[dict[str, Any]]:
    """One row per local calendar day in [since, until), zero-filled."""
    zone = ZoneInfo(tz)
    rows = {
        row["day"]: row
        for row in incidents_in(user, window)
        .annotate(day=TruncDate("triggered_at", tzinfo=zone))
        .values("day")
        .annotate(
            incidents=Count("pk"),
            high=Count("pk", filter=Q(urgency=Urgency.HIGH)),
            low=Count("pk", filter=Q(urgency=Urgency.LOW)),
            time_to_first_response=Avg(
                _elapsed("first_response_at"), filter=Q(first_response_at__isnull=False)
            ),
            mtta=Avg(_elapsed("acknowledged_at"), filter=Q(acknowledged_at__isnull=False)),
            mttr=Avg(_elapsed("resolved_at"), filter=Q(resolved_at__isnull=False)),
        )
    }
    day: date = window.since.astimezone(zone).date()
    last: date = (window.until - timedelta(microseconds=1)).astimezone(zone).date()
    series = []
    while day <= last:
        row: dict[str, Any] = dict(rows.get(day, {}))
        series.append(
            {
                "date": day,
                "incidents": row.get("incidents", 0),
                "high": row.get("high", 0),
                "low": row.get("low", 0),
                "time_to_first_response_seconds": _seconds(row.get("time_to_first_response")),
                "mtta_seconds": _seconds(row.get("mtta")),
                "mttr_seconds": _seconds(row.get("mttr")),
            }
        )
        day += timedelta(days=1)
    return series
