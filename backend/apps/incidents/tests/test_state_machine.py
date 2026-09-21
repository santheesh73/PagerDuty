import pytest
from django.utils import timezone

from apps.incidents.exceptions import IncidentReopenConflict, IncidentStateConflict
from apps.incidents.models import Incident, IncidentEvent
from apps.incidents.services import (
    acknowledge_incident,
    reopen_incident,
    resolve_incident,
)
from apps.services.models import Service
from apps.users.models import Team, User


@pytest.fixture
def service():
    team = Team.objects.create(name="Core Backend", slug="core-backend")
    return Service.objects.create(name="Order Service", slug="order-service", team=team)


@pytest.fixture
def user():
    return User.objects.create(username="operator_bob", email="bob@example.com")


@pytest.fixture
def incident(service):
    return Incident.objects.create(
        service=service,
        title="Latency spike on /orders",
        severity=Incident.Severity.CRITICAL,
        fingerprint="f" * 64,
    )


@pytest.mark.django_db
def test_acknowledge_lifecycle(incident, user):
    """Verify acknowledge transitions from TRIGGERED to ACKNOWLEDGED and is idempotent."""
    assert incident.status == Incident.Status.TRIGGERED
    assert incident.acknowledged_at is None

    # First acknowledge
    acked = acknowledge_incident(incident, user=user)
    assert acked.status == Incident.Status.ACKNOWLEDGED
    assert acked.acknowledged_at is not None
    orig_acked_at = acked.acknowledged_at

    # Verify event
    assert IncidentEvent.objects.filter(
        incident=incident,
        event_type=IncidentEvent.EventType.INCIDENT_ACKNOWLEDGED,
        actor=user,
    ).count() == 1

    # Second acknowledge (idempotency)
    re_acked = acknowledge_incident(incident, user=user)
    assert re_acked.status == Incident.Status.ACKNOWLEDGED
    assert re_acked.acknowledged_at == orig_acked_at
    assert IncidentEvent.objects.filter(
        incident=incident,
        event_type=IncidentEvent.EventType.INCIDENT_ACKNOWLEDGED,
    ).count() == 1


@pytest.mark.django_db
def test_acknowledge_resolved_incident_rejected(incident, user):
    """Verify acknowledging a resolved incident is rejected with IncidentStateConflict."""
    incident = resolve_incident(incident, user=user)
    assert incident.status == Incident.Status.RESOLVED

    with pytest.raises(IncidentStateConflict, match="already RESOLVED"):
        acknowledge_incident(incident, user=user)


@pytest.mark.django_db
def test_resolve_from_triggered(incident, user):
    """Verify direct resolution from TRIGGERED without prior acknowledgement is allowed."""
    resolved = resolve_incident(incident, user=user)
    assert resolved.status == Incident.Status.RESOLVED
    assert resolved.resolved_at is not None
    assert resolved.acknowledged_at is None

    assert IncidentEvent.objects.filter(
        incident=incident,
        event_type=IncidentEvent.EventType.INCIDENT_RESOLVED,
        actor=user,
    ).count() == 1


@pytest.mark.django_db
def test_resolve_from_acknowledged_and_idempotency(incident, user):
    """Verify resolution from ACKNOWLEDGED and idempotency on duplicate resolve calls."""
    acknowledge_incident(incident, user=user)
    resolved = resolve_incident(incident, user=user)
    assert resolved.status == Incident.Status.RESOLVED
    assert resolved.resolved_at is not None
    orig_resolved_at = resolved.resolved_at

    # Idempotent re-resolve
    re_resolved = resolve_incident(incident, user=user)
    assert re_resolved.status == Incident.Status.RESOLVED
    assert re_resolved.resolved_at == orig_resolved_at
    assert IncidentEvent.objects.filter(
        incident=incident,
        event_type=IncidentEvent.EventType.INCIDENT_RESOLVED,
    ).count() == 1


@pytest.mark.django_db
def test_reopen_lifecycle(incident, user):
    """Verify reopening a RESOLVED incident resets lifecycle and captures historical metadata."""
    incident = acknowledge_incident(incident, user=user)
    incident = resolve_incident(incident, user=user)
    assert incident.status == Incident.Status.RESOLVED

    # Reopen
    reopened = reopen_incident(incident, user=user)
    assert reopened.status == Incident.Status.TRIGGERED
    assert reopened.triggered_at is not None
    assert reopened.acknowledged_at is None
    assert reopened.resolved_at is None

    reopen_event = IncidentEvent.objects.get(
        incident=incident,
        event_type=IncidentEvent.EventType.INCIDENT_REOPENED,
    )
    assert reopen_event.actor == user
    assert "previous_resolved_at" in reopen_event.metadata


@pytest.mark.django_db
def test_reopen_non_resolved_rejected(incident, user):
    """Verify reopening an active incident (TRIGGERED) raises IncidentStateConflict."""
    with pytest.raises(IncidentStateConflict, match="only RESOLVED incidents can be reopened"):
        reopen_incident(incident, user=user)


@pytest.mark.django_db
def test_reopen_with_existing_active_incident_conflict(service, user):
    """
    Verify that if an active incident already exists for (service, fingerprint),
    attempting to reopen a historical resolved incident cleanly raises IncidentReopenConflict.
    """
    fingerprint = "reopen_test_fingerprint"
    # Resolved incident 1
    old_inc = Incident.objects.create(
        service=service,
        title="Historical outage",
        severity=Incident.Severity.HIGH,
        fingerprint=fingerprint,
        status=Incident.Status.RESOLVED,
        resolved_at=timezone.now(),
    )

    # Active incident 2 currently open
    Incident.objects.create(
        service=service,
        title="Active outage",
        severity=Incident.Severity.HIGH,
        fingerprint=fingerprint,
        status=Incident.Status.TRIGGERED,
        resolved_at=None,
    )

    # Attempting to reopen old_inc must raise domain conflict
    with pytest.raises(IncidentReopenConflict, match="active incident already exists"):
        reopen_incident(old_inc, user=user)
