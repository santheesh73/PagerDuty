from celery import shared_task
from django.utils import timezone

from . import engine


@shared_task(acks_late=True)
def escalate_incident(incident_id: int, level: int, loop: int) -> bool:
    return engine.escalate(incident_id, level, loop, timezone.now())


@shared_task
def sweep_due_escalations() -> int:
    return engine.sweep(timezone.now())
