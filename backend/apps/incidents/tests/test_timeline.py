import pytest
from django.db.models.deletion import ProtectedError

from apps.alerts.models import Alert
from apps.alerts.triage import triage_alert
from apps.incidents.models import Incident, IncidentEvent
from apps.services.models import Service
from apps.users.models import Team


@pytest.fixture
def service():
    team = Team.objects.create(name="Infrastructure", slug="infra")
    return Service.objects.create(name="Cache Service", slug="cache-service", team=team)


@pytest.mark.django_db
def test_timeline_event_sequence_for_new_and_duplicate_alerts(service):
    """
    Verify event ordering:
    - New incident creates INCIDENT_TRIGGERED, then ALERT_ATTACHED.
    - Subsequent duplicate alert appends ALERT_ATTACHED without duplicate INCIDENT_TRIGGERED.
    """
    fingerprint = "timeline_fp_123"
    a1 = Alert.objects.create(
        service=service,
        severity=Alert.Severity.HIGH,
        message="Redis connection timeout",
        source="datadog",
        fingerprint=fingerprint,
    )
    inc = triage_alert(a1)
    events_1 = list(inc.events.all().order_by("created_at", "id"))
    assert len(events_1) == 2
    assert events_1[0].event_type == IncidentEvent.EventType.INCIDENT_TRIGGERED
    assert events_1[0].metadata["initial_alert_id"] == a1.id
    assert events_1[1].event_type == IncidentEvent.EventType.ALERT_ATTACHED
    assert events_1[1].metadata["alert_id"] == a1.id

    # Duplicate alert arrives
    a2 = Alert.objects.create(
        service=service,
        severity=Alert.Severity.HIGH,
        message="Redis connection timeout",
        source="datadog",
        fingerprint=fingerprint,
    )
    inc2 = triage_alert(a2)
    assert inc2.id == inc.id

    events_2 = list(inc.events.all().order_by("created_at", "id"))
    assert len(events_2) == 3
    assert events_2[2].event_type == IncidentEvent.EventType.ALERT_ATTACHED
    assert events_2[2].metadata["alert_id"] == a2.id


@pytest.mark.django_db
def test_incident_deletion_protected_when_events_exist(service):
    """
    Verify that deleting an Incident with existing events is prevented by on_delete=PROTECT.
    Historical audit logs cannot be silently cascaded away.
    """
    inc = Incident.objects.create(
        service=service,
        title="Production incident with timeline",
        severity=Incident.Severity.CRITICAL,
        fingerprint="protected_fp",
    )
    IncidentEvent.objects.create(
        incident=inc,
        event_type=IncidentEvent.EventType.INCIDENT_TRIGGERED,
    )

    with pytest.raises(ProtectedError):
        inc.delete()
