"""Events API ingest: one monitoring event in, one incident created or updated.

Dedup is a *database* guarantee, not an application one. "Look for an open incident, else
create one" races: two identical alerts arriving together can both see nothing and both
create. The partial unique index `uniq_open_incident_per_dedup_key` makes the second insert
fail; we catch that and retry once, and the retry finds — and attaches to — the winner.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.catalog.models import Service
from apps.core.errors import Conflict, InvalidTransition
from apps.core.locks import advisory_xact_lock
from apps.core.text import one_line
from apps.incidents import actions as incident_actions
from apps.incidents.models import Incident, Status, Urgency

from .models import Alert, Severity

logger = logging.getLogger(__name__)

MAINTENANCE_DEDUP_KEY = "__maintenance__"

URGENCY_FOR_SEVERITY = {
    Severity.CRITICAL: Urgency.HIGH,
    Severity.ERROR: Urgency.HIGH,
    Severity.WARNING: Urgency.LOW,
    Severity.INFO: Urgency.LOW,
}


class IngestConflict(Conflict):
    code = "ingest_conflict"


@dataclass(frozen=True)
class Event:
    action: str  # trigger | acknowledge | resolve
    dedup_key: str | None = None
    summary: str = ""
    severity: str = Severity.CRITICAL
    source: str = ""
    custom_details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IngestResult:
    status: str  # accepted | ignored
    dedup_key: str
    incident_id: int | None = None
    created: bool = False


def ingest(service: Service, event: Event, *, now: datetime | None = None) -> IngestResult:
    now = now or timezone.now()
    if event.action == "trigger":
        return _trigger(service, event, now)
    return _source_transition(service, event, now)


def _trigger(service: Service, event: Event, now: datetime) -> IngestResult:
    dedup_key = event.dedup_key or uuid.uuid4().hex
    in_maintenance = service.mode == Service.Mode.MAINTENANCE
    incident_key = MAINTENANCE_DEDUP_KEY if in_maintenance else dedup_key
    urgency = URGENCY_FOR_SEVERITY[Severity(event.severity)]

    for attempt in (1, 2):
        try:
            with transaction.atomic():
                # Serialise open-or-attach per key. Without it, a loser re-reads, finds nothing
                # open (the winner was resolved meanwhile), inserts, and loses again; under
                # sustained churn two attempts were not enough and the alert was dropped (409).
                # The unique index below stays as the backstop.
                advisory_xact_lock("incident-key", service.pk, incident_key)
                incident = (
                    Incident.objects.select_for_update(no_key=True, of=("self",))
                    .filter(service=service, dedup_key=incident_key)
                    .exclude(status=Status.RESOLVED)
                    .first()
                )
                alert = Alert.objects.create(
                    service=service,
                    dedup_key=dedup_key,
                    severity=event.severity,
                    summary=event.summary[:1024],
                    source=event.source[:255],
                    payload={"custom_details": event.custom_details},
                    status=Alert.Status.SUPPRESSED if in_maintenance else Alert.Status.TRIGGERED,
                    received_at=now,
                )
                created = incident is None
                if incident is None:
                    incident = incident_actions.open_incident(
                        service,
                        dedup_key=incident_key,
                        title=(
                            f"Maintenance: {service.name}"
                            if in_maintenance
                            else one_line(event.summary)
                        ),
                        urgency=urgency,
                        now=now,
                        is_maintenance=in_maintenance,
                    )
                alert.incident = incident
                alert.save(update_fields=["incident", "updated_at"])
                if not created:
                    incident_actions.attach_alert(incident, alert)
                return IngestResult("accepted", dedup_key, incident.pk, created)
        except IntegrityError:
            # Lost the race to open this incident; the second pass will attach instead.
            logger.info(
                "dedup race lost; retrying as attach",
                extra={"service_id": service.pk, "attempt": attempt},
            )
    raise IngestConflict("Could not attach the alert to an incident; please retry.")


def _source_transition(service: Service, event: Event, now: datetime) -> IngestResult:
    """acknowledge / resolve from the monitoring system. Never counts as a human response."""
    dedup_key = event.dedup_key or ""
    incident = (
        Incident.objects.filter(service=service, dedup_key=dedup_key)
        .exclude(status=Status.RESOLVED)
        .only("pk")
        .first()
    )
    if incident is None:
        return IngestResult("ignored", dedup_key)
    transition = (
        incident_actions.acknowledge if event.action == "acknowledge" else incident_actions.resolve
    )
    try:
        transition(incident.pk, actor=None, now=now, via=event.source or "events_api")
    except InvalidTransition:
        return IngestResult("ignored", dedup_key, incident.pk)
    return IngestResult("accepted", dedup_key, incident.pk)
