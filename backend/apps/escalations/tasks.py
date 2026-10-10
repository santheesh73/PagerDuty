import logging

from celery import shared_task
from django.utils import timezone

from . import engine

logger = logging.getLogger(__name__)


@shared_task(acks_late=True)
def escalate_incident(incident_id: int, level: int, loop: int) -> bool:
    return engine.escalate(incident_id, level, loop, timezone.now())


@shared_task
def sweep_due_escalations() -> int:
    now = timezone.now()
    moved = 0
    for incident_id, level, loop in engine.due_incidents(now):
        try:
            moved += engine.escalate(incident_id, level, loop, now)
        except Exception:
            # One bad incident must not stall paging for every other incident.
            logger.exception("sweep escalation failed", extra={"incident_id": incident_id})
    return moved
