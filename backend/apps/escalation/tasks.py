import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.incidents.models import Incident, IncidentEvent
from apps.incidents.services import record_incident_event
from apps.notifications.services import create_notification
from apps.notifications.tasks import dispatch_notification

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def check_and_escalate(
    self,
    incident_id: int,
    expected_level_id: int,
    expected_generation: int,
) -> bool:
    """
    Core escalation task executing after a level's wait_minutes timer expires.
    Guarantees:
    - Atomicity & row locking via select_for_update().
    - Live state reload: checks incident.status == TRIGGERED.
    - Expected-level check: avoids double-advancing if duplicate tasks run concurrently.
    - Automation-generation check: discards stale tasks from previous lifecycles on reopen.
    - Records immutable timeline transitions (INCIDENT_ESCALATED or ESCALATION_EXHAUSTED).
    - Asynchronously dispatches notification and schedules next check on commit.
    """
    from .services import resolve_escalation_target, schedule_escalation_check

    with transaction.atomic():
        incident = (
            Incident.objects.select_for_update()
            .filter(pk=incident_id)
            .first()
        )
        if not incident:
            logger.warning("check_and_escalate: Incident %s not found.", incident_id)
            return False

        # 1. State check: ACKNOWLEDGED or RESOLVED halts escalation
        if incident.status != Incident.Status.TRIGGERED:
            logger.info(
                "check_and_escalate: Incident INC-%s is in status '%s' (not TRIGGERED). Escalation halted.",
                incident.id,
                incident.status,
            )
            return False

        # 2. Lifecycle generation check: protects against stale tasks across reopen cycles
        if incident.automation_generation != expected_generation:
            logger.info(
                "check_and_escalate: Generation mismatch for INC-%s (expected %s, got %s). Stale task discarded.",
                incident.id,
                expected_generation,
                incident.automation_generation,
            )
            return False

        # 3. Expected level check: protects against duplicate task execution skipping levels
        if incident.current_escalation_level_id != expected_level_id:
            logger.info(
                "check_and_escalate: Level mismatch for INC-%s (expected level %s, got %s). Task ignored.",
                incident.id,
                expected_level_id,
                incident.current_escalation_level_id,
            )
            return False

        current_level = incident.current_escalation_level
        if not current_level:
            logger.warning("check_and_escalate: Incident INC-%s has no current escalation level.", incident.id)
            return False

        # 4. Resolve next escalation level
        next_level = (
            current_level.policy.levels.filter(order__gt=current_level.order)
            .order_by("order")
            .first()
        )

        # 5. Final level handling: record ESCALATION_EXHAUSTED once and halt
        if not next_level:
            already_exhausted = incident.events.filter(
                event_type=IncidentEvent.EventType.ESCALATION_EXHAUSTED,
                metadata__generation=incident.automation_generation,
            ).exists()
            if not already_exhausted:
                record_incident_event(
                    incident=incident,
                    event_type=IncidentEvent.EventType.ESCALATION_EXHAUSTED,
                    actor=None,
                    metadata={
                        "policy_id": current_level.policy_id,
                        "final_level_id": current_level.id,
                        "final_order": current_level.order,
                        "generation": incident.automation_generation,
                    },
                )
                logger.info("check_and_escalate: Escalation policy exhausted for INC-%s.", incident.id)
            return False

        # 6. Resolve target for next level at current escalation time
        now = timezone.now()
        next_target = resolve_escalation_target(incident, next_level, now)

        if not next_target:
            incident.current_escalation_level = next_level
            incident.save(update_fields=["current_escalation_level", "updated_at"])
            record_incident_event(
                incident=incident,
                event_type=IncidentEvent.EventType.ESCALATION_TARGET_UNAVAILABLE,
                actor=None,
                metadata={
                    "level_id": next_level.id,
                    "order": next_level.order,
                    "target_type": next_level.target_type,
                    "reason": "target_user_unavailable",
                    "generation": incident.automation_generation,
                },
            )
            logger.warning(
                "check_and_escalate: Target unavailable for Level %s on INC-%s.",
                next_level.order,
                incident.id,
            )
            schedule_escalation_check(incident, next_level)
            return False

        # 7. Atomically advance escalation level and reassign responder
        previous_user = incident.assigned_user
        incident.current_escalation_level = next_level
        incident.assigned_user = next_target
        incident.save(update_fields=["current_escalation_level", "assigned_user", "updated_at"])

        # 8. Record escalation event
        record_incident_event(
            incident=incident,
            event_type=IncidentEvent.EventType.INCIDENT_ESCALATED,
            actor=None,
            metadata={
                "from_level": current_level.id,
                "to_level": next_level.id,
                "from_order": current_level.order,
                "to_order": next_level.order,
                "previous_user_id": previous_user.id if previous_user else None,
                "new_user_id": next_target.id,
                "generation": incident.automation_generation,
            },
        )

        # 9. Create notification and enqueue asynchronous dispatch on transaction commit
        notification = create_notification(
            incident=incident,
            recipient=next_target,
            escalation_level=next_level,
            channel="EMAIL",
        )
        transaction.on_commit(lambda: dispatch_notification.delay(notification.id))

        # 10. Schedule check for subsequent level
        schedule_escalation_check(incident, next_level)

        logger.info(
            "check_and_escalate: Escalated INC-%s from Level %s to Level %s (assignee=%s)",
            incident.id,
            current_level.order,
            next_level.order,
            next_target.username,
        )
        return True
