import concurrent.futures

import pytest
from django.db import connection

from apps.alerts.models import Alert
from apps.alerts.triage import triage_alert
from apps.incidents.models import Incident, IncidentEvent
from apps.incidents.services import acknowledge_incident
from apps.services.models import Service
from apps.users.models import Team, User


@pytest.fixture
def service():
    team = Team.objects.create(name="Concurrency Team", slug="concurrency-team")
    return Service.objects.create(name="Worker API", slug="worker-api", team=team)


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_alerts_deduplicate_to_single_incident(service):
    """
    Section 43: Concurrency-safe deduplication test.
    Simulate two identical alerts for the same service and fingerprint being triaged concurrently.
    Expected:
    - Exactly 1 active Incident created.
    - Both alerts linked to that same Incident.
    - No unhandled IntegrityError or uniqueness corruption.
    """
    fingerprint = "concurrent_fp_test_123"
    a1 = Alert.objects.create(
        service=service,
        severity=Alert.Severity.CRITICAL,
        message="504 Gateway Timeout",
        source="alb",
        fingerprint=fingerprint,
    )
    a2 = Alert.objects.create(
        service=service,
        severity=Alert.Severity.CRITICAL,
        message="504 Gateway Timeout",
        source="alb",
        fingerprint=fingerprint,
    )

    def run_triage(alert_id):
        connection.close()  # Ensure separate thread DB connection
        alert = Alert.objects.get(pk=alert_id)
        return triage_alert(alert)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(run_triage, a1.id)
        f2 = executor.submit(run_triage, a2.id)
        inc1 = f1.result()
        inc2 = f2.result()

    # Both must resolve to the identical incident
    assert inc1.id == inc2.id

    # Verify database state
    active_incidents = Incident.objects.filter(
        service=service,
        fingerprint=fingerprint,
        resolved_at__isnull=True,
    )
    assert active_incidents.count() == 1

    a1.refresh_from_db()
    a2.refresh_from_db()
    assert a1.incident_id == inc1.id
    assert a2.incident_id == inc1.id

    # Events: 1 INCIDENT_TRIGGERED and 2 ALERT_ATTACHED
    events = list(inc1.events.all())
    triggered_events = [e for e in events if e.event_type == IncidentEvent.EventType.INCIDENT_TRIGGERED]
    attached_events = [e for e in events if e.event_type == IncidentEvent.EventType.ALERT_ATTACHED]
    assert len(triggered_events) == 1
    assert len(attached_events) == 2


@pytest.mark.django_db(transaction=True)
def test_simultaneous_acknowledgement_first_write_wins(service):
    """
    Section 45: Simultaneous acknowledgement test.
    Two users acknowledge the same TRIGGERED incident concurrently.
    Expected:
    - Exactly one transition to ACKNOWLEDGED.
    - Exactly one INCIDENT_ACKNOWLEDGED event recorded.
    - Timestamp acknowledged_at set once.
    - Second request behaves idempotently without state corruption.
    """
    user_alice = User.objects.create(username="alice_ack", email="alice@example.com")
    user_bob = User.objects.create(username="bob_ack", email="bob@example.com")

    incident = Incident.objects.create(
        service=service,
        title="Concurrent ACK race",
        severity=Incident.Severity.HIGH,
        fingerprint="ack_fp_race",
    )

    def run_ack(user_id):
        connection.close()
        user = User.objects.get(pk=user_id)
        inc = Incident.objects.get(pk=incident.pk)
        return acknowledge_incident(inc, user=user)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(run_ack, user_alice.id)
        f2 = executor.submit(run_ack, user_bob.id)
        res1 = f1.result()
        res2 = f2.result()

    assert res1.status == Incident.Status.ACKNOWLEDGED
    assert res2.status == Incident.Status.ACKNOWLEDGED

    incident.refresh_from_db()
    assert incident.status == Incident.Status.ACKNOWLEDGED
    assert incident.acknowledged_at is not None

    # Exactly 1 INCIDENT_ACKNOWLEDGED event exists
    ack_events = IncidentEvent.objects.filter(
        incident=incident,
        event_type=IncidentEvent.EventType.INCIDENT_ACKNOWLEDGED,
    )
    assert ack_events.count() == 1
    assert ack_events.first().actor in [user_alice, user_bob]
