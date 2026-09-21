import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from apps.incidents.models import Incident, IncidentEvent
from apps.services.models import Service
from apps.users.models import Team, User


@pytest.fixture
def service():
    team = Team.objects.create(name="Platform Ops", slug="platform-ops")
    return Service.objects.create(name="Billing API", slug="billing-api", team=team)


@pytest.mark.django_db
def test_create_valid_incident(service):
    """Verify standard creation of an Incident with default fields."""
    incident = Incident.objects.create(
        service=service,
        title="High error rate on /checkout",
        severity=Incident.Severity.CRITICAL,
        fingerprint="a" * 64,
    )
    assert incident.id is not None
    assert incident.service == service
    assert incident.status == Incident.Status.TRIGGERED
    assert incident.assigned_user is None
    assert incident.triggered_at is not None
    assert incident.acknowledged_at is None
    assert incident.resolved_at is None
    assert "INC-" in str(incident)
    assert "High error rate" in str(incident)


@pytest.mark.django_db
def test_incident_with_assigned_user(service):
    """Verify assigned_user relationship can be assigned or remain null."""
    user = User.objects.create(username="responder1")
    incident = Incident.objects.create(
        service=service,
        title="Database failover alert",
        severity=Incident.Severity.HIGH,
        fingerprint="b" * 64,
        assigned_user=user,
    )
    assert incident.assigned_user == user


@pytest.mark.django_db
def test_active_incident_uniqueness_constraint(service):
    """
    Verify PostgreSQL-compatible conditional uniqueness constraint:
    Only ONE unresolved Incident per (service, fingerprint) is permitted.
    """
    fingerprint = "c" * 64
    # First active incident
    Incident.objects.create(
        service=service,
        title="Primary incident",
        severity=Incident.Severity.HIGH,
        fingerprint=fingerprint,
        resolved_at=None,
    )

    # Second active incident with identical service & fingerprint must violate constraint
    with pytest.raises(IntegrityError):
        Incident.objects.create(
            service=service,
            title="Duplicate active incident",
            severity=Incident.Severity.HIGH,
            fingerprint=fingerprint,
            resolved_at=None,
        )


@pytest.mark.django_db
def test_resolved_incident_allows_new_incident_with_same_fingerprint(service):
    """
    Verify that resolving an incident (resolved_at populated) frees the partial unique constraint,
    allowing a new incident with the same (service, fingerprint).
    """
    fingerprint = "d" * 64
    old_incident = Incident.objects.create(
        service=service,
        title="Historical incident",
        severity=Incident.Severity.HIGH,
        fingerprint=fingerprint,
        status=Incident.Status.RESOLVED,
        resolved_at=timezone.now(),
    )
    assert old_incident.resolved_at is not None

    # Creating a new active incident must succeed
    new_incident = Incident.objects.create(
        service=service,
        title="New active incident",
        severity=Incident.Severity.HIGH,
        fingerprint=fingerprint,
        status=Incident.Status.TRIGGERED,
        resolved_at=None,
    )
    assert new_incident.id is not None
    assert new_incident.id != old_incident.id


@pytest.mark.django_db
def test_incident_event_append_only_protection(service):
    """
    Verify IncidentEvent append-only invariant:
    Updates and direct deletions are prevented.
    """
    incident = Incident.objects.create(
        service=service,
        title="Event audit test",
        severity=Incident.Severity.LOW,
        fingerprint="e" * 64,
    )
    event = IncidentEvent.objects.create(
        incident=incident,
        event_type=IncidentEvent.EventType.INCIDENT_TRIGGERED,
        metadata={"note": "initial"},
    )
    assert event.id is not None

    # Attempted update must be blocked
    event.metadata = {"note": "tampered"}
    with pytest.raises(ValidationError, match="append-only and cannot be modified"):
        event.save()

    # Attempted direct delete must be blocked
    with pytest.raises(ValidationError, match="append-only and cannot be deleted"):
        event.delete()
