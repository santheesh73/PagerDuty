"""Data retention: delete what is old enough that nobody needs it, in small batches.

Off unless `RETENTION_DAYS` > 0, because deleting history is not something to do by default and
analytics (MTTA/MTTR, trends) are computed from it. What goes: resolved incidents resolved more
than N days ago, with their timeline, notifications and alerts (alerts are SET_NULL on the
incident FK, so they are removed explicitly), plus alerts old enough that they never joined an
incident. Open incidents are never touched, however old. Expired sessions are cleared too, since
that is housekeeping, not history.
"""

import logging
from datetime import datetime, timedelta

from django.contrib.sessions.models import Session
from django.utils import timezone

from apps.alerting.models import Alert
from apps.incidents.models import Incident, Status

logger = logging.getLogger(__name__)

BATCH = 500  # small deletes keep each transaction (and its locks) short


def purge(days: int, *, now: datetime | None = None) -> dict[str, int]:
    """Delete data older than `days`. Returns counts; a no-op for days <= 0."""
    if days <= 0:
        return {"incidents": 0, "alerts": 0}
    cutoff = (now or timezone.now()) - timedelta(days=days)
    incidents = alerts = 0
    while True:
        ids = list(
            Incident.objects.filter(status=Status.RESOLVED, resolved_at__lt=cutoff)
            .order_by("resolved_at")
            .values_list("pk", flat=True)[:BATCH]
        )
        if not ids:
            break
        alerts += Alert.objects.filter(incident_id__in=ids).delete()[0]
        Incident.objects.filter(pk__in=ids).delete()
        incidents += len(ids)
    while True:
        ids = list(
            Alert.objects.filter(incident__isnull=True, received_at__lt=cutoff).values_list(
                "pk", flat=True
            )[:BATCH]
        )
        if not ids:
            break
        alerts += Alert.objects.filter(pk__in=ids).delete()[0]
    logger.info("retention purge", extra={"days": days, "incidents": incidents, "alerts": alerts})
    return {"incidents": incidents, "alerts": alerts}


def clear_expired_sessions(*, now: datetime | None = None) -> int:
    return Session.objects.filter(expire_date__lt=now or timezone.now()).delete()[0]
