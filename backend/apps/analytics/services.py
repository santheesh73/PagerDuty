from datetime import timedelta

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F
from django.utils import timezone

from apps.incidents.models import Incident


def parse_range_param(range_str: str | None) -> int:
    """Parses range param (e.g. '7d', '30d', '90d') to integer days. Defaults to 30."""
    if not range_str:
        return 30
    cleaned = range_str.lower().strip()
    if cleaned.endswith("d"):
        cleaned = cleaned[:-1]
    try:
        days = int(cleaned)
        return max(1, min(days, 365))
    except (ValueError, TypeError):
        return 30


def get_base_incident_queryset(days: int | None = 30):
    qs = Incident.objects.all()
    if days:
        since = timezone.now() - timedelta(days=days)
        qs = qs.filter(triggered_at__gte=since)
    return qs


def calculate_analytics_summary(days: int = 30) -> dict:
    """
    Computes system-level incident metrics:
    - MTTA: Average time between triggered_at and acknowledged_at for acknowledged incidents.
    - MTTR: Average time between triggered_at and resolved_at for resolved incidents.
    """
    qs = get_base_incident_queryset(days)

    total_count = qs.count()
    active_count = qs.filter(resolved_at__isnull=True).count()
    critical_count = qs.filter(severity=Incident.Severity.CRITICAL).count()

    # Calculate MTTA
    ack_qs = qs.filter(acknowledged_at__isnull=False)
    mtta_duration = ack_qs.annotate(
        tt_ack=ExpressionWrapper(F("acknowledged_at") - F("triggered_at"), output_field=DurationField())
    ).aggregate(avg_ack=Avg("tt_ack"))["avg_ack"]

    mtta_seconds = None
    if mtta_duration is not None:
        mtta_seconds = round(mtta_duration.total_seconds(), 1)

    # Calculate MTTR
    res_qs = qs.filter(resolved_at__isnull=False)
    mttr_duration = res_qs.annotate(
        tt_res=ExpressionWrapper(F("resolved_at") - F("triggered_at"), output_field=DurationField())
    ).aggregate(avg_res=Avg("tt_res"))["avg_res"]

    mttr_seconds = None
    if mttr_duration is not None:
        mttr_seconds = round(mttr_duration.total_seconds(), 1)

    return {
        "range_days": days,
        "incident_count": total_count,
        "active_incidents": active_count,
        "critical_incidents": critical_count,
        "mtta_seconds": mtta_seconds,
        "mttr_seconds": mttr_seconds,
    }


def calculate_incidents_by_service(days: int = 30) -> list[dict]:
    """Calculates incident volume grouped by affected service."""
    qs = get_base_incident_queryset(days)

    results = (
        qs.values("service_id", "service__name")
        .annotate(count=Count("id"))
        .order_by("-count", "service__name")
    )

    return [
        {
            "service_id": item["service_id"],
            "service_name": item["service__name"] or f"Service #{item['service_id']}",
            "count": item["count"],
        }
        for item in results
    ]


def calculate_severity_distribution(days: int = 30) -> list[dict]:
    """Calculates incident distribution by severity level."""
    qs = get_base_incident_queryset(days)

    counts_by_sev = {
        item["severity"].lower(): item["count"]
        for item in qs.values("severity").annotate(count=Count("id"))
    }

    # Ensure all canonical severity levels are represented
    order = ["critical", "high", "medium", "low"]
    return [{"severity": sev, "count": counts_by_sev.get(sev, 0)} for sev in order]


def calculate_incident_trend(days: int = 30) -> list[dict]:
    """Calculates daily incident creation volume across the requested day range."""
    qs = get_base_incident_queryset(days)

    now = timezone.now()
    daily_counts: dict[str, int] = {}
    for i in range(days - 1, -1, -1):
        d_str = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        daily_counts[d_str] = 0

    # Group in python to avoid SQLite/Postgres date truncation dialect differences
    for inc in qs.only("triggered_at"):
        d_str = inc.triggered_at.strftime("%Y-%m-%d")
        if d_str in daily_counts:
            daily_counts[d_str] += 1

    return [{"date": k, "count": v} for k, v in daily_counts.items()]
