from datetime import datetime
from typing import TYPE_CHECKING, Any

from django.utils import timezone

from apps.scheduling.exceptions import InvalidTimestampError

if TYPE_CHECKING:
    from django.contrib.auth import get_user_model

    from apps.incidents.models import Incident
    from apps.scheduling.models import Schedule
    from apps.services.models import Service

    User = get_user_model()


def get_on_call(schedule: "Schedule", timestamp: datetime) -> "User | None":
    """
    Deterministically computes the active on-call user for a given Schedule at an explicit timestamp.
    - Timestamp must be timezone-aware (UTC-safe).
    - Overrides take strict precedence over base rotations.
    - Operates on half-open intervals: start_time <= timestamp < end_time.
    - If schedule is inactive or no rotation covers timestamp, returns None.
    """
    assignment = get_on_call_assignment(schedule, timestamp)
    return assignment["user"] if assignment else None


def get_on_call_assignment(schedule: "Schedule", timestamp: datetime) -> dict[str, Any] | None:
    """
    Resolves the active on-call assignment metadata for a Schedule at an explicit timestamp.
    Returns:
        {
            "user": User,
            "rotation": ScheduleRotation,
            "source": "override" | "base",
        }
    or None if no user is on call.
    """
    if timestamp is None or timezone.is_naive(timestamp):
        raise InvalidTimestampError("Timestamp must be a timezone-aware datetime.")

    if not schedule.is_active:
        return None

    # 1. Check override rotations first (half-open: start_time <= timestamp < end_time)
    override = (
        schedule.rotations.filter(
            is_override=True,
            start_time__lte=timestamp,
            end_time__gt=timestamp,
        )
        .select_related("user")
        .order_by("-start_time", "-id")
        .first()
    )
    if override:
        return {
            "user": override.user,
            "rotation": override,
            "source": "override",
        }

    # 2. Check base rotations (half-open: start_time <= timestamp < end_time)
    base = (
        schedule.rotations.filter(
            is_override=False,
            start_time__lte=timestamp,
            end_time__gt=timestamp,
        )
        .select_related("user")
        .order_by("-start_time", "-id")
        .first()
    )
    if base:
        return {
            "user": base.user,
            "rotation": base,
            "source": "base",
        }

    return None


def get_current_on_call(schedule: "Schedule") -> "User | None":
    """Convenience wrapper resolving on-call user at current server time."""
    return get_on_call(schedule, timezone.now())


def get_routing_schedule(service: "Service") -> "Schedule | None":
    """
    Resolves the operational Schedule for an incident by traversing Service -> Team -> Schedule.
    Retrieves the unique active primary Schedule for the owning Team.
    """
    if not service or not service.team_id:
        return None

    return (
        service.team.schedules.filter(
            is_primary=True,
            is_active=True,
        )
        .first()
    )


def assign_incident_on_creation(
    incident: "Incident",
    timestamp: datetime | None = None,
) -> "Incident":
    """
    Automatically resolves and assigns an on-call responder when an incident is newly created.
    - Idempotent: If incident already has an assigned_user, leaves it unchanged.
    - Uses incident.triggered_at (or explicit timestamp) for deterministic shift resolution.
    - If team has no active primary schedule, or schedule has no active rotation, records
      ROUTING_UNAVAILABLE timeline event and leaves assigned_user as None.
    - If an on-call user is found, sets assigned_user and records RESPONDER_ASSIGNED event.
    """
    from apps.incidents.models import IncidentEvent
    from apps.incidents.services import record_incident_event

    # Idempotency check: preserve existing assignee
    if incident.assigned_user_id is not None:
        return incident

    ts = timestamp or incident.triggered_at or timezone.now()
    if timezone.is_naive(ts):
        raise InvalidTimestampError("Timestamp must be a timezone-aware datetime.")

    schedule = get_routing_schedule(incident.service)
    if not schedule:
        record_incident_event(
            incident=incident,
            event_type=IncidentEvent.EventType.ROUTING_UNAVAILABLE,
            actor=None,
            metadata={
                "reason": "no_primary_schedule",
                "service_id": incident.service_id,
            },
        )
        return incident

    assignment = get_on_call_assignment(schedule, ts)
    if not assignment:
        record_incident_event(
            incident=incident,
            event_type=IncidentEvent.EventType.ROUTING_UNAVAILABLE,
            actor=None,
            metadata={
                "reason": "no_active_rotation",
                "schedule_id": schedule.id,
            },
        )
        return incident

    on_call_user = assignment["user"]
    incident.assigned_user = on_call_user
    incident.save(update_fields=["assigned_user", "updated_at"])

    record_incident_event(
        incident=incident,
        event_type=IncidentEvent.EventType.RESPONDER_ASSIGNED,
        actor=None,
        metadata={
            "user_id": on_call_user.id,
            "username": on_call_user.username,
            "schedule_id": schedule.id,
            "rotation_id": assignment["rotation"].id,
            "source": assignment["source"],
        },
    )
    return incident
