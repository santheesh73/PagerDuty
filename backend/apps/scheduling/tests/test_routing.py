from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from apps.alerts.models import Alert
from apps.alerts.triage import triage_alert
from apps.incidents.models import Incident, IncidentEvent
from apps.scheduling.models import Schedule, ScheduleRotation
from apps.scheduling.services import assign_incident_on_creation
from apps.services.models import Service
from apps.users.models import Team, TeamMembership, User


@pytest.fixture
def routing_setup(db):
    team = Team.objects.create(name="Backend Team", slug="backend-team")
    alice = User.objects.create_user(username="alice")
    bob = User.objects.create_user(username="bob")
    TeamMembership.objects.create(team=team, user=alice)
    TeamMembership.objects.create(team=team, user=bob)

    service = Service.objects.create(
        name="Payment API",
        slug="payment-api",
        team=team,
        status=Service.Status.HEALTHY,
    )

    schedule = Schedule.objects.create(
        name="Backend Primary",
        slug="backend-primary",
        team=team,
        timezone="UTC",
        is_primary=True,
        is_active=True,
    )

    # Base: Alice 09:00 - 17:00
    ScheduleRotation.objects.create(
        schedule=schedule,
        user=alice,
        start_time=datetime(2026, 9, 21, 9, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 9, 21, 17, 0, 0, tzinfo=UTC),
        is_override=False,
    )

    # Base: Bob 17:00 - 01:00 (next day)
    ScheduleRotation.objects.create(
        schedule=schedule,
        user=bob,
        start_time=datetime(2026, 9, 21, 17, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 9, 22, 1, 0, 0, tzinfo=UTC),
        is_override=False,
    )

    return {
        "team": team,
        "alice": alice,
        "bob": bob,
        "service": service,
        "schedule": schedule,
    }


@pytest.mark.django_db
def test_automatic_routing_on_new_incident_creation(routing_setup):
    service = routing_setup["service"]
    alice = routing_setup["alice"]

    fixed_now = datetime(2026, 9, 21, 10, 0, 0, tzinfo=UTC)
    with patch("django.utils.timezone.now", return_value=fixed_now):
        alert = Alert.objects.create(
            service=service,
            severity=Alert.Severity.CRITICAL,
            message="Payment gateway timeout",
            source="payment-monitor",
        )
        incident = triage_alert(alert)

    assert incident.assigned_user == alice
    assert incident.status == Incident.Status.TRIGGERED

    # Timeline event sequence
    event_types = list(incident.events.values_list("event_type", flat=True))
    assert event_types == [
        IncidentEvent.EventType.INCIDENT_TRIGGERED,
        IncidentEvent.EventType.ALERT_ATTACHED,
        IncidentEvent.EventType.RESPONDER_ASSIGNED,
    ]

    assign_event = incident.events.filter(event_type=IncidentEvent.EventType.RESPONDER_ASSIGNED).first()
    assert assign_event.metadata["user_id"] == alice.id
    assert assign_event.metadata["username"] == "alice"
    assert assign_event.metadata["schedule_id"] == routing_setup["schedule"].id


@pytest.mark.django_db
def test_assignment_stability_when_duplicate_alert_attaches_mid_rotation(routing_setup):
    """
    Mandatory Section 43:
    09:30: Alice on call -> Incident created -> Alice assigned.
    10:00: Shift rotates to Bob.
    10:05: Duplicate Alert arrives and attaches to active Incident.
    Expected:
    Incident.assigned_user remains Alice!
    No second assignment event!
    """
    service = routing_setup["service"]
    alice = routing_setup["alice"]
    bob = routing_setup["bob"]
    schedule = routing_setup["schedule"]

    # 1. 09:30: Alert 1 arrives, Alice on-call
    t_0930 = datetime(2026, 9, 21, 9, 30, 0, tzinfo=UTC)
    with patch("django.utils.timezone.now", return_value=t_0930):
        alert1 = Alert.objects.create(
            service=service,
            severity=Alert.Severity.CRITICAL,
            message="Payment gateway timeout",
            source="payment-monitor",
        )
        incident = triage_alert(alert1)

    assert incident.assigned_user == alice
    initial_event_count = incident.events.count()

    # 2. Add an override at 10:00 making Bob on call
    ScheduleRotation.objects.create(
        schedule=schedule,
        user=bob,
        start_time=datetime(2026, 9, 21, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC),
        is_override=True,
    )

    # 3. 10:05: Duplicate Alert arrives
    t_1005 = datetime(2026, 9, 21, 10, 5, 0, tzinfo=UTC)
    with patch("django.utils.timezone.now", return_value=t_1005):
        alert2 = Alert.objects.create(
            service=service,
            severity=Alert.Severity.CRITICAL,
            message="Payment gateway timeout",
            source="payment-monitor",
        )
        same_incident = triage_alert(alert2)

    assert same_incident.id == incident.id
    # Assigned user is STABLE, Alice remains assigned
    assert same_incident.assigned_user == alice
    # Only 1 new event: ALERT_ATTACHED (no second RESPONDER_ASSIGNED event)
    assert same_incident.events.count() == initial_event_count + 1
    assert same_incident.events.filter(event_type=IncidentEvent.EventType.RESPONDER_ASSIGNED).count() == 1


@pytest.mark.django_db
def test_no_on_call_responder_records_routing_unavailable(routing_setup):
    service = routing_setup["service"]

    # Trigger at 03:00 (outside all rotation windows)
    t_0300 = datetime(2026, 9, 21, 3, 0, 0, tzinfo=UTC)
    with patch("django.utils.timezone.now", return_value=t_0300):
        alert = Alert.objects.create(
            service=service,
            severity=Alert.Severity.HIGH,
            message="High latency in queue",
            source="worker-monitor",
        )
        incident = triage_alert(alert)

    assert incident.assigned_user is None
    event_types = list(incident.events.values_list("event_type", flat=True))
    assert event_types == [
        IncidentEvent.EventType.INCIDENT_TRIGGERED,
        IncidentEvent.EventType.ALERT_ATTACHED,
        IncidentEvent.EventType.ROUTING_UNAVAILABLE,
    ]
    unavail_event = incident.events.filter(event_type=IncidentEvent.EventType.ROUTING_UNAVAILABLE).first()
    assert unavail_event.metadata["reason"] == "no_active_rotation"


@pytest.mark.django_db
def test_no_primary_schedule_records_routing_unavailable(routing_setup):
    service = routing_setup["service"]
    schedule = routing_setup["schedule"]
    schedule.is_primary = False
    schedule.save()

    t_1000 = datetime(2026, 9, 21, 10, 0, 0, tzinfo=UTC)
    with patch("django.utils.timezone.now", return_value=t_1000):
        alert = Alert.objects.create(
            service=service,
            severity=Alert.Severity.MEDIUM,
            message="Database cache miss spike",
            source="db-monitor",
        )
        incident = triage_alert(alert)

    assert incident.assigned_user is None
    unavail_event = incident.events.filter(event_type=IncidentEvent.EventType.ROUTING_UNAVAILABLE).first()
    assert unavail_event.metadata["reason"] == "no_primary_schedule"


@pytest.mark.django_db
def test_routing_idempotency(routing_setup):
    service = routing_setup["service"]
    alice = routing_setup["alice"]

    t = datetime(2026, 9, 21, 10, 0, 0, tzinfo=UTC)
    incident = Incident.objects.create(
        service=service,
        title="Test Incident",
        severity=Incident.Severity.CRITICAL,
        status=Incident.Status.TRIGGERED,
        fingerprint="fp123",
        triggered_at=t,
    )

    # First call assigns
    assign_incident_on_creation(incident, t)
    assert incident.assigned_user == alice
    assert incident.events.filter(event_type=IncidentEvent.EventType.RESPONDER_ASSIGNED).count() == 1

    # Second call does not duplicate
    assign_incident_on_creation(incident, t)
    assert incident.assigned_user == alice
    assert incident.events.filter(event_type=IncidentEvent.EventType.RESPONDER_ASSIGNED).count() == 1


@pytest.mark.django_db
def test_override_routing_assigns_override_user(routing_setup):
    service = routing_setup["service"]
    schedule = routing_setup["schedule"]
    bob = routing_setup["bob"]

    # Bob has override 12:00 - 14:00
    ScheduleRotation.objects.create(
        schedule=schedule,
        user=bob,
        start_time=datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 9, 21, 14, 0, 0, tzinfo=UTC),
        is_override=True,
    )

    t_1300 = datetime(2026, 9, 21, 13, 0, 0, tzinfo=UTC)
    with patch("django.utils.timezone.now", return_value=t_1300):
        alert = Alert.objects.create(
            service=service,
            severity=Alert.Severity.CRITICAL,
            message="Service outage during lunch",
            source="synthetic-check",
        )
        incident = triage_alert(alert)

    assert incident.assigned_user == bob
    assign_event = incident.events.filter(event_type=IncidentEvent.EventType.RESPONDER_ASSIGNED).first()
    assert assign_event.metadata["source"] == "override"
    assert assign_event.metadata["user_id"] == bob.id
