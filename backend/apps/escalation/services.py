from datetime import datetime
import logging
from typing import TYPE_CHECKING, Any

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.incidents.models import IncidentEvent
from apps.incidents.services import record_incident_event
from apps.notifications.services import create_notification
from apps.notifications.tasks import dispatch_notification
from apps.scheduling.services import get_on_call, get_routing_schedule

from .models import EscalationLevel, EscalationPolicy

if TYPE_CHECKING:
    from apps.incidents.models import Incident
    from apps.services.models import Service

User = get_user_model()
logger = logging.getLogger(__name__)


def find_escalation_policy(service: "Service") -> EscalationPolicy | None:
    """
    Authoritatively resolves the active EscalationPolicy configured for a given Service.
    Rules:
    1. Service explicitly references policy.
    2. Policy must be active.
    3. Policy Team must match Service Team.
    Returns the EscalationPolicy if valid, else None.
    """
    if not service or not service.escalation_policy_id:
        return None

    policy = service.escalation_policy
    if not policy.is_active:
        logger.warning("Service %s references inactive EscalationPolicy %s", service.id, policy.id)
        return None

    if policy.team_id != service.team_id:
        logger.warning(
            "Service %s team (%s) does not match EscalationPolicy %s team (%s)",
            service.id,
            service.team_id,
            policy.id,
            policy.team_id,
        )
        return None

    return policy


def resolve_escalation_target(
    incident: "Incident",
    escalation_level: EscalationLevel,
    timestamp: datetime,
) -> Any | None:
    """
    Deterministically computes the recipient User for an EscalationLevel.
    - CURRENT_ON_CALL: Traverses Service -> Team -> Primary Schedule -> get_on_call(schedule, timestamp).
    - USER: Resolves target_user if active.
    """
    if escalation_level.target_type == EscalationLevel.TargetType.CURRENT_ON_CALL:
        schedule = get_routing_schedule(incident.service)
        if not schedule:
            logger.warning(
                "Cannot resolve CURRENT_ON_CALL: no active primary schedule for team %s",
                incident.service.team_id,
            )
            return None
        return get_on_call(schedule, timestamp)

    if escalation_level.target_type == EscalationLevel.TargetType.USER:
        target_user = escalation_level.target_user
        if target_user and target_user.is_active:
            return target_user
        return None

    return None


def assign_and_notify(
    incident: "Incident",
    user: Any,
    escalation_level: EscalationLevel,
    is_initial: bool = False,
) -> None:
    """
    Updates incident responder assignment and current escalation level,
    appends RESPONDER_ASSIGNED timeline event, and enqueues a notification dispatch.
    """
    previous_user = incident.assigned_user
    incident.assigned_user = user
    incident.current_escalation_level = escalation_level
    incident.save(update_fields=["assigned_user", "current_escalation_level", "updated_at"])

    # Avoid duplicate responder assigned event if user has not changed on non-initial steps
    if is_initial or previous_user != user:
        record_incident_event(
            incident=incident,
            event_type=IncidentEvent.EventType.RESPONDER_ASSIGNED,
            actor=None,
            metadata={
                "user_id": user.id,
                "username": user.username,
                "escalation_level_id": escalation_level.id,
                "level_order": escalation_level.order,
                "is_initial": is_initial,
            },
        )

    notification = create_notification(
        incident=incident,
        recipient=user,
        escalation_level=escalation_level,
        channel="EMAIL",
    )
    transaction.on_commit(lambda: dispatch_notification.delay(notification.id))


def schedule_escalation_check(
    incident: "Incident",
    current_level: EscalationLevel,
) -> None:
    """
    Schedules an asynchronous Celery task to verify whether the incident requires
    escalation after wait_minutes elapses.
    Tasks are enqueued inside transaction.on_commit to ensure database persistence.
    """
    from .tasks import check_and_escalate

    transaction.on_commit(
        lambda: check_and_escalate.apply_async(
            args=[incident.id, current_level.id, incident.automation_generation],
            countdown=current_level.wait_minutes * 60,
        )
    )


def start_incident_escalation(
    incident: "Incident",
    timestamp: datetime | None = None,
) -> bool:
    """
    Initiates Level 1 escalation automation for a newly created or reopened incident.
    - Resolves escalation policy for the service.
    - If no policy exists: falls back to Phase 4 primary schedule responder routing.
    - If policy exists: starts Level 1 automation (target resolution, assign, notify, schedule check).
    """
    policy = find_escalation_policy(incident.service)
    ts = timestamp or incident.triggered_at or timezone.now()

    if not policy:
        # Fallback to Phase 4 schedule routing when no escalation policy is configured
        from apps.scheduling.services import assign_incident_on_creation

        assign_incident_on_creation(incident, ts)
        return False

    level_1 = policy.levels.order_by("order").first()
    if not level_1:
        logger.warning("EscalationPolicy %s has no configured levels.", policy.id)
        record_incident_event(
            incident=incident,
            event_type=IncidentEvent.EventType.ESCALATION_TARGET_UNAVAILABLE,
            actor=None,
            metadata={
                "reason": "no_levels_in_policy",
                "policy_id": policy.id,
            },
        )
        return False

    record_incident_event(
        incident=incident,
        event_type=IncidentEvent.EventType.ESCALATION_STARTED,
        actor=None,
        metadata={
            "policy_id": policy.id,
            "policy_name": policy.name,
            "initial_level_id": level_1.id,
            "generation": incident.automation_generation,
        },
    )

    target_user = resolve_escalation_target(incident, level_1, ts)
    if not target_user:
        incident.current_escalation_level = level_1
        incident.save(update_fields=["current_escalation_level", "updated_at"])
        record_incident_event(
            incident=incident,
            event_type=IncidentEvent.EventType.ESCALATION_TARGET_UNAVAILABLE,
            actor=None,
            metadata={
                "level_id": level_1.id,
                "order": level_1.order,
                "target_type": level_1.target_type,
                "reason": "no_on_call_or_target_user",
            },
        )
        # Even if target user was unavailable at Level 1, schedule check for Level 2
        schedule_escalation_check(incident, level_1)
        return False

    assign_and_notify(incident, target_user, level_1, is_initial=True)
    schedule_escalation_check(incident, level_1)
    return True
