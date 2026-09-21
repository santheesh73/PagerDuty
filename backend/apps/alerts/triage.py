import hashlib
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.alerts.models import Alert
    from apps.incidents.models import Incident


def normalize_alert_source(source: str) -> str:
    """
    Normalizes the alert source string.
    Trims surrounding whitespace and converts to lower case.
    """
    return source.strip().lower()


def normalize_alert_message(message: str) -> str:
    """
    Normalizes the alert message string.
    Trims leading/trailing whitespace and collapses internal multiple whitespace runs
    into a single space, without modifying error codes, IDs, or tokens.
    """
    trimmed = message.strip()
    return re.sub(r"\s+", " ", trimmed)


def build_alert_fingerprint(service_id: int | str, source: str, message: str) -> str:
    """
    Generates a deterministic SHA-256 fingerprint for alert grouping and deduplication.
    Formula: SHA-256(service_id:normalized_source:normalized_message).
    Omits received_at so identical events recurring across time share the same fingerprint.
    """
    norm_source = normalize_alert_source(source)
    norm_message = normalize_alert_message(message)
    payload = f"{service_id}:{norm_source}:{norm_message}".encode()
    return hashlib.sha256(payload).hexdigest()


def triage_alert(alert: "Alert") -> "Incident":
    """
    Triages an incoming Alert into an Incident.
    - If alert is already linked to an incident, returns it (idempotent).
    - Looks for an active (unresolved) Incident for the same (service, fingerprint).
    - If found: attaches alert to existing incident and records ALERT_ATTACHED.
    - If none found: creates new Incident (status=TRIGGERED), records INCIDENT_TRIGGERED,
      attaches alert, and records ALERT_ATTACHED.
    - Concurrency-safe: uses transaction.atomic(), select_for_update(), and recovers
      from IntegrityError on the partial unique active-incident constraint.
    """
    from django.db import IntegrityError, transaction
    from django.utils import timezone

    from apps.alerts.models import Alert
    from apps.incidents.models import Incident, IncidentEvent
    from apps.incidents.services import record_incident_event

    # Fast path if already triaged outside transaction
    if alert.incident_id:
        return alert.incident

    with transaction.atomic():
        locked_alert = (
            Alert.objects.select_for_update()
            .select_related("service")
            .get(pk=alert.pk)
        )
        if locked_alert.incident_id:
            return locked_alert.incident

        incident = (
            Incident.objects.select_for_update()
            .filter(
                service=locked_alert.service,
                fingerprint=locked_alert.fingerprint,
                resolved_at__isnull=True,
            )
            .first()
        )

        is_new_incident = False
        if not incident:
            try:
                with transaction.atomic():
                    incident = Incident.objects.create(
                        service=locked_alert.service,
                        title=locked_alert.message[:255],
                        severity=locked_alert.severity,
                        status=Incident.Status.TRIGGERED,
                        fingerprint=locked_alert.fingerprint,
                        assigned_user=None,
                        triggered_at=timezone.now(),
                    )
                    record_incident_event(
                        incident=incident,
                        event_type=IncidentEvent.EventType.INCIDENT_TRIGGERED,
                        actor=None,
                        metadata={"initial_alert_id": locked_alert.id},
                    )
                    is_new_incident = True
            except IntegrityError:
                # Concurrent race condition: another transaction created active incident first
                incident = (
                    Incident.objects.select_for_update()
                    .get(
                        service=locked_alert.service,
                        fingerprint=locked_alert.fingerprint,
                        resolved_at__isnull=True,
                    )
                )

        locked_alert.incident = incident
        locked_alert.save(update_fields=["incident"])

        record_incident_event(
            incident=incident,
            event_type=IncidentEvent.EventType.ALERT_ATTACHED,
            actor=None,
            metadata={
                "alert_id": locked_alert.id,
                "fingerprint": locked_alert.fingerprint,
            },
        )

        if is_new_incident:
            from apps.scheduling.services import assign_incident_on_creation

            assign_incident_on_creation(incident, incident.triggered_at)

        return incident

