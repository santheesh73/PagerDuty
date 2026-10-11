"""Database-checkable invariants from docs/INVARIANTS.md, in one place.

`check_invariants()` returns a list of human-readable violations (empty means healthy).
The fault simulator calls it after every operation; tests can call `assert_invariants()`.
Invariants that need history the database doesn't keep (I4's "delivered at most once",
I7's "advanced on the next sweep", I10's per-operation event counts) are checked by the
simulator itself, which observes every operation.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from django.db.models import Count, Q

from apps.incidents.models import EventType, Incident, IncidentEvent, Status
from apps.notifications.actions import page_key
from apps.notifications.models import Notification

# Human actions that count as a first response (incidents/actions.py::FIRST_RESPONSE_ACTIONS).
FIRST_RESPONSE_EVENTS = (
    EventType.ACKNOWLEDGED,
    EventType.UNACKNOWLEDGED,
    EventType.RESOLVED,
    EventType.MAINTENANCE_ENDED,  # a human resolving a maintenance incident
    EventType.REASSIGNED,
    EventType.MANUAL_ESCALATED,
)
# Timeline entries that are delivery receipts, not state transitions (I10 excludes them).
DELIVERY_EVENTS = (EventType.NOTIFIED, EventType.NOTIFICATION_FAILED)


@dataclass(frozen=True)
class Violation:
    invariant: str
    incident_id: int | None
    detail: str

    def __str__(self) -> str:
        where = f" incident={self.incident_id}" if self.incident_id else ""
        return f"{self.invariant}{where}: {self.detail}"


class InvariantViolation(AssertionError):
    pass


def check_invariants(incident_ids: Iterable[int] | None = None) -> list[Violation]:
    """Check I1, I5, I6, I8, I9, I13 against current database state.

    `incident_ids` limits the per-incident checks to those incidents (the simulator passes
    the ones an operation touched); global checks always run.
    """
    incidents = Incident.objects.all()
    if incident_ids is not None:
        incidents = incidents.filter(pk__in=list(incident_ids))
    violations: list[Violation] = []
    violations += _i1_one_open_incident_per_key()
    for incident in incidents.select_related("service"):
        violations += _i8_only_triggered_incidents_have_timers(incident)
        violations += _i13_maintenance_never_pages(incident)
        violations += _i9_first_response_is_human(incident)
        violations += _i5_every_paged_responder_has_a_row(incident)
        violations += _i6_bounded_automatic_steps(incident)
    return violations


def assert_invariants(incident_ids: Iterable[int] | None = None) -> None:
    violations = check_invariants(incident_ids)
    if violations:
        raise InvariantViolation("\n".join(str(v) for v in violations))


# --- individual checks -------------------------------------------------------------------


def _i1_one_open_incident_per_key() -> list[Violation]:
    duplicates = (
        Incident.objects.exclude(status=Status.RESOLVED)
        .values("service_id", "dedup_key")
        .annotate(n=Count("pk"))
        .filter(n__gt=1)
    )
    return [
        Violation(
            "I1",
            None,
            f"{row['n']} open incidents for service {row['service_id']} key {row['dedup_key']!r}",
        )
        for row in duplicates
    ]


def _i8_only_triggered_incidents_have_timers(incident: Incident) -> list[Violation]:
    if incident.status != Status.TRIGGERED and incident.next_escalation_at is not None:
        return [
            Violation(
                "I8",
                incident.pk,
                f"{incident.status} but timer at {incident.next_escalation_at.isoformat()}",
            )
        ]
    return []


def _i13_maintenance_never_pages(incident: Incident) -> list[Violation]:
    if not incident.is_maintenance:
        return []
    found = []
    if incident.next_escalation_at is not None:
        found.append(Violation("I13", incident.pk, "maintenance incident has a timer"))
    pages = incident.notifications.count()
    if pages:
        found.append(Violation("I13", incident.pk, f"maintenance incident has {pages} pages"))
    return found


def _i9_first_response_is_human(incident: Incident) -> list[Violation]:
    human = incident.events.filter(type__in=FIRST_RESPONSE_EVENTS, actor__isnull=False)
    earliest = human.order_by("created_at", "pk").values_list("created_at", flat=True).first()
    if incident.first_response_at is None:
        if earliest is not None:
            return [
                Violation("I9", incident.pk, "a human responded but first_response_at is not set")
            ]
        return []
    if earliest is None:
        return [
            Violation(
                "I9", incident.pk, "first_response_at set without any human first-response event"
            )
        ]
    if earliest != incident.first_response_at:
        return [
            Violation(
                "I9",
                incident.pk,
                f"first_response_at "
                f"{incident.first_response_at.isoformat()} != first "
                f"human response {earliest.isoformat()}",
            )
        ]
    return []


def _i5_every_paged_responder_has_a_row(incident: Incident) -> list[Violation]:
    """Every responder a paging event names has rows for that page, including the inbox entry.

    Which other channels exist depends on the person's own plan (snapshotted per page), so the
    check is "the page was planned at all": rows sharing the page's `page_key`, one of them in-app.
    """
    if incident.is_maintenance:
        return []
    pairs = set(incident.notifications.values_list("page_key", "channel"))
    found = []
    paging = incident.events.filter(
        Q(type__in=[EventType.TRIGGERED, EventType.ESCALATED, EventType.MANUAL_ESCALATED])
        | Q(type__in=[EventType.UNACKNOWLEDGED, EventType.REASSIGNED])
    )
    for event in paging:
        data = event.data or {}
        recipients = data.get("to")
        if recipients is None:
            continue
        recipients = recipients if isinstance(recipients, list) else [recipients]
        for user_id in recipients:
            if event.type in (EventType.UNACKNOWLEDGED, EventType.REASSIGNED):
                tail = f":user:{user_id}:seq:{event.pk}"
                channels = {
                    c
                    for k, c in pairs
                    if k.startswith(f"incident:{incident.pk}:") and k.endswith(tail)
                }
            else:
                wanted = page_key(
                    incident.pk, data.get("level", 0), data.get("loop", 0), user_id, None
                )
                channels = {c for k, c in pairs if k == wanted}
            if "in_app" not in channels:
                found.append(
                    Violation(
                        "I5",
                        incident.pk,
                        f"{event.type} event {event.pk} paged user {user_id} "
                        f"but no inbox row exists for that page",
                    )
                )
    return found


def _i6_bounded_automatic_steps(incident: Incident) -> list[Violation]:
    """Between human interventions, automatic steps never exceed levels * (loops + 1)."""
    snapshot = incident.escalation_snapshot or {}
    positions = len(snapshot.get("rules") or []) * (snapshot.get("num_loops", 0) + 1)
    resets = {
        EventType.ACKNOWLEDGED,
        EventType.UNACKNOWLEDGED,
        EventType.REASSIGNED,
        EventType.MANUAL_ESCALATED,
    }
    steps = worst = 0
    for event_type, actor_id in incident.events.order_by("created_at", "pk").values_list(
        "type", "actor_id"
    ):
        if event_type in resets and actor_id is not None:
            steps = 0
        elif event_type in (EventType.ESCALATED, EventType.NO_RESPONDER) and actor_id is None:
            steps += 1
            worst = max(worst, steps)
    if worst > positions:
        return [
            Violation(
                "I6",
                incident.pk,
                f"{worst} automatic steps without a human, but the "
                f"policy has only {positions} positions",
            )
        ]
    return []


def non_delivery_event_count(incident_ids: Iterable[int] | None = None) -> int:
    events = IncidentEvent.objects.exclude(type__in=DELIVERY_EVENTS)
    if incident_ids is not None:
        events = events.filter(incident_id__in=list(incident_ids))
    return events.count()


def pending_notifications() -> int:
    return Notification.objects.filter(status=Notification.Status.PENDING).count()
