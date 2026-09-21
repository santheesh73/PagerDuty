from typing import Any

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from .exceptions import IncidentReopenConflict, IncidentStateConflict
from .models import Incident, IncidentEvent

User = get_user_model()


def record_incident_event(
    *,
    incident: Incident,
    event_type: str,
    actor: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> IncidentEvent:
    """
    Centralized service to append an immutable event entry to the incident timeline.
    """
    clean_actor = actor if getattr(actor, "is_authenticated", False) else None
    return IncidentEvent.objects.create(
        incident=incident,
        event_type=event_type,
        actor=clean_actor,
        metadata=metadata or {},
        created_at=timezone.now(),
    )


def acknowledge_incident(
    incident: Incident,
    user: Any | None = None,
) -> Incident:
    """
    Transitions an incident from TRIGGERED to ACKNOWLEDGED.
    Enforces concurrency-safety (select_for_update) and first-write-wins idempotency.
    """
    with transaction.atomic():
        locked_incident = (
            Incident.objects.select_for_update()
            .select_related("service")
            .get(pk=incident.pk)
        )

        if locked_incident.status == Incident.Status.TRIGGERED:
            locked_incident.status = Incident.Status.ACKNOWLEDGED
            if not locked_incident.acknowledged_at:
                locked_incident.acknowledged_at = timezone.now()
            locked_incident.save(update_fields=["status", "acknowledged_at", "updated_at"])

            record_incident_event(
                incident=locked_incident,
                event_type=IncidentEvent.EventType.INCIDENT_ACKNOWLEDGED,
                actor=user,
            )
            return locked_incident

        if locked_incident.status == Incident.Status.ACKNOWLEDGED:
            # Idempotent: return without updating timestamp or creating duplicate event
            return locked_incident

        if locked_incident.status == Incident.Status.RESOLVED:
            raise IncidentStateConflict(
                f"Cannot acknowledge incident INC-{locked_incident.id}: incident is already RESOLVED."
            )

        raise IncidentStateConflict(
            f"Unexpected status '{locked_incident.status}' for incident INC-{locked_incident.id}."
        )


def resolve_incident(
    incident: Incident,
    user: Any | None = None,
) -> Incident:
    """
    Transitions an incident to RESOLVED.
    Allowed directly from TRIGGERED or ACKNOWLEDGED.
    Idempotent if already RESOLVED.
    """
    with transaction.atomic():
        locked_incident = (
            Incident.objects.select_for_update()
            .select_related("service")
            .get(pk=incident.pk)
        )

        if locked_incident.status in [
            Incident.Status.TRIGGERED,
            Incident.Status.ACKNOWLEDGED,
        ]:
            locked_incident.status = Incident.Status.RESOLVED
            locked_incident.resolved_at = timezone.now()
            locked_incident.save(update_fields=["status", "resolved_at", "updated_at"])

            record_incident_event(
                incident=locked_incident,
                event_type=IncidentEvent.EventType.INCIDENT_RESOLVED,
                actor=user,
            )
            return locked_incident

        if locked_incident.status == Incident.Status.RESOLVED:
            # Idempotent: return without updating timestamp or duplicating event
            return locked_incident

        raise IncidentStateConflict(
            f"Unexpected status '{locked_incident.status}' for incident INC-{locked_incident.id}."
        )


def reopen_incident(
    incident: Incident,
    user: Any | None = None,
) -> Incident:
    """
    Explicitly transitions a RESOLVED incident back to TRIGGERED.
    Resets lifecycle timestamps and captures previous state in timeline metadata.
    Enforces active-incident uniqueness (rejects if active incident exists for same service/fingerprint).
    """
    with transaction.atomic():
        locked_incident = (
            Incident.objects.select_for_update()
            .select_related("service")
            .get(pk=incident.pk)
        )

        if locked_incident.status != Incident.Status.RESOLVED:
            raise IncidentStateConflict(
                f"Cannot reopen incident INC-{locked_incident.id}: only RESOLVED incidents can be reopened (current status: '{locked_incident.status}')."
            )

        # Check if another active incident exists for the same service and fingerprint
        active_conflict = (
            Incident.objects.filter(
                service=locked_incident.service,
                fingerprint=locked_incident.fingerprint,
                resolved_at__isnull=True,
            )
            .exclude(pk=locked_incident.pk)
            .exists()
        )
        if active_conflict:
            raise IncidentReopenConflict(
                f"Cannot reopen incident INC-{locked_incident.id}: an active incident already exists for service '{locked_incident.service.name}' and fingerprint '{locked_incident.fingerprint}'."
            )

        metadata = {
            "previous_triggered_at": (
                locked_incident.triggered_at.isoformat()
                if locked_incident.triggered_at
                else None
            ),
            "previous_acknowledged_at": (
                locked_incident.acknowledged_at.isoformat()
                if locked_incident.acknowledged_at
                else None
            ),
            "previous_resolved_at": (
                locked_incident.resolved_at.isoformat()
                if locked_incident.resolved_at
                else None
            ),
        }

        locked_incident.status = Incident.Status.TRIGGERED
        locked_incident.triggered_at = timezone.now()
        locked_incident.acknowledged_at = None
        locked_incident.resolved_at = None
        locked_incident.current_escalation_level = None
        locked_incident.automation_generation += 1

        try:
            locked_incident.save(
                update_fields=[
                    "status",
                    "triggered_at",
                    "acknowledged_at",
                    "resolved_at",
                    "current_escalation_level",
                    "automation_generation",
                    "updated_at",
                ]
            )
        except IntegrityError:
            raise IncidentReopenConflict(
                f"Cannot reopen incident INC-{locked_incident.id}: active incident uniqueness conflict for service '{locked_incident.service.name}' and fingerprint '{locked_incident.fingerprint}'."
            )

        record_incident_event(
            incident=locked_incident,
            event_type=IncidentEvent.EventType.INCIDENT_REOPENED,
            actor=user,
            metadata=metadata,
        )

        if locked_incident.service.escalation_policy_id:
            from apps.escalation.services import start_incident_escalation

            start_incident_escalation(locked_incident, locked_incident.triggered_at)

        return locked_incident
