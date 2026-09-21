from datetime import datetime, timezone as dt_timezone
import pytest
from unittest.mock import patch

from apps.alerts.models import Alert
from apps.alerts.triage import triage_alert
from apps.incidents.models import IncidentEvent
from apps.scheduling.exceptions import RotationOverlapError
from apps.scheduling.models import Schedule, ScheduleRotation
from apps.scheduling.services import get_on_call
from apps.services.models import Service
from apps.users.models import Team, TeamMembership, User


@pytest.fixture
def golden_setup(db):
    team = Team.objects.create(name="Backend Team", slug="backend-team")
    alice = User.objects.create_user(username="alice", first_name="Alice")
    bob = User.objects.create_user(username="bob", first_name="Bob")
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

    # Base rotations:
    # Alice: 09:00 <= t < 17:00
    r_alice = ScheduleRotation.objects.create(
        schedule=schedule,
        user=alice,
        start_time=datetime(2026, 9, 21, 9, 0, 0, tzinfo=dt_timezone.utc),
        end_time=datetime(2026, 9, 21, 17, 0, 0, tzinfo=dt_timezone.utc),
        is_override=False,
    )

    # Bob: 17:00 <= t < 23:00
    r_bob = ScheduleRotation.objects.create(
        schedule=schedule,
        user=bob,
        start_time=datetime(2026, 9, 21, 17, 0, 0, tzinfo=dt_timezone.utc),
        end_time=datetime(2026, 9, 21, 23, 0, 0, tzinfo=dt_timezone.utc),
        is_override=False,
    )

    return {
        "team": team,
        "alice": alice,
        "bob": bob,
        "service": service,
        "schedule": schedule,
        "r_alice": r_alice,
        "r_bob": r_bob,
    }


@pytest.mark.django_db
def test_scenario_a_incident_triggered_at_1000(golden_setup):
    """Scenario A: Incident triggered at 10:00 -> Alice assigned."""
    service = golden_setup["service"]
    alice = golden_setup["alice"]

    t_1000 = datetime(2026, 9, 21, 10, 0, 0, tzinfo=dt_timezone.utc)
    with patch("django.utils.timezone.now", return_value=t_1000):
        alert = Alert.objects.create(
            service=service,
            severity=Alert.Severity.CRITICAL,
            message="Payment API 500 error",
            source="monitoring",
        )
        incident = triage_alert(alert)

    assert incident.assigned_user == alice
    assign_event = incident.events.filter(event_type=IncidentEvent.EventType.RESPONDER_ASSIGNED).first()
    assert assign_event is not None
    assert assign_event.metadata["user_id"] == alice.id


@pytest.mark.django_db
def test_scenario_b_override_at_1300(golden_setup):
    """Scenario B: Override Bob 12:00-14:00, Incident triggered at 13:00 -> Bob assigned."""
    service = golden_setup["service"]
    schedule = golden_setup["schedule"]
    bob = golden_setup["bob"]

    ScheduleRotation.objects.create(
        schedule=schedule,
        user=bob,
        start_time=datetime(2026, 9, 21, 12, 0, 0, tzinfo=dt_timezone.utc),
        end_time=datetime(2026, 9, 21, 14, 0, 0, tzinfo=dt_timezone.utc),
        is_override=True,
    )

    t_1300 = datetime(2026, 9, 21, 13, 0, 0, tzinfo=dt_timezone.utc)
    with patch("django.utils.timezone.now", return_value=t_1300):
        alert = Alert.objects.create(
            service=service,
            severity=Alert.Severity.CRITICAL,
            message="DB connection pool exhausted",
            source="db-monitor",
        )
        incident = triage_alert(alert)

    assert incident.assigned_user == bob
    assign_event = incident.events.filter(event_type=IncidentEvent.EventType.RESPONDER_ASSIGNED).first()
    assert assign_event.metadata["user_id"] == bob.id
    assert assign_event.metadata["source"] == "override"


@pytest.mark.django_db
def test_scenario_c_assignment_stability_mid_incident(golden_setup):
    """
    Scenario C:
    Incident created at 10:00 (Alice assigned).
    Schedule changes at 11:00 (Bob becomes on-call).
    Duplicate Alert at 11:30.
    Expected: same Incident, assigned_user remains Alice, NO second assignment event.
    """
    service = golden_setup["service"]
    schedule = golden_setup["schedule"]
    alice = golden_setup["alice"]
    bob = golden_setup["bob"]

    # 1. 10:00 Incident created
    t_1000 = datetime(2026, 9, 21, 10, 0, 0, tzinfo=dt_timezone.utc)
    with patch("django.utils.timezone.now", return_value=t_1000):
        alert1 = Alert.objects.create(
            service=service,
            severity=Alert.Severity.CRITICAL,
            message="Payment API 500 error",
            source="monitoring",
        )
        incident = triage_alert(alert1)

    assert incident.assigned_user == alice
    initial_event_count = incident.events.count()

    # 2. Schedule changes at 11:00 (Bob override 11:00 - 15:00)
    ScheduleRotation.objects.create(
        schedule=schedule,
        user=bob,
        start_time=datetime(2026, 9, 21, 11, 0, 0, tzinfo=dt_timezone.utc),
        end_time=datetime(2026, 9, 21, 15, 0, 0, tzinfo=dt_timezone.utc),
        is_override=True,
    )

    # 3. Duplicate Alert at 11:30
    t_1130 = datetime(2026, 9, 21, 11, 30, 0, tzinfo=dt_timezone.utc)
    with patch("django.utils.timezone.now", return_value=t_1130):
        alert2 = Alert.objects.create(
            service=service,
            severity=Alert.Severity.CRITICAL,
            message="Payment API 500 error",
            source="monitoring",
        )
        same_incident = triage_alert(alert2)

    assert same_incident.id == incident.id
    assert same_incident.assigned_user == alice
    assert same_incident.events.count() == initial_event_count + 1
    assert same_incident.events.filter(event_type=IncidentEvent.EventType.RESPONDER_ASSIGNED).count() == 1


@pytest.mark.django_db
def test_scenario_d_no_matching_rotation(golden_setup):
    """Scenario D: Incident triggered at 02:00 -> No rotation matches -> assigned_user=null, no crash."""
    service = golden_setup["service"]

    t_0200 = datetime(2026, 9, 21, 2, 0, 0, tzinfo=dt_timezone.utc)
    with patch("django.utils.timezone.now", return_value=t_0200):
        alert = Alert.objects.create(
            service=service,
            severity=Alert.Severity.HIGH,
            message="Nightly batch memory warning",
            source="cron",
        )
        incident = triage_alert(alert)

    assert incident.id is not None
    assert incident.assigned_user is None
    unavail = incident.events.filter(event_type=IncidentEvent.EventType.ROUTING_UNAVAILABLE).first()
    assert unavail is not None


@pytest.mark.django_db
def test_scenario_e_exact_boundary_handoff(golden_setup):
    """
    Scenario E:
    Alice ends 17:00, Bob starts 17:00.
    Incident triggered 17:00 exactly -> Bob assigned.
    """
    service = golden_setup["service"]
    bob = golden_setup["bob"]

    t_1700 = datetime(2026, 9, 21, 17, 0, 0, tzinfo=dt_timezone.utc)
    with patch("django.utils.timezone.now", return_value=t_1700):
        alert = Alert.objects.create(
            service=service,
            severity=Alert.Severity.CRITICAL,
            message="Spike at shift change",
            source="gateway",
        )
        incident = triage_alert(alert)

    assert incident.assigned_user == bob


@pytest.mark.django_db
def test_scenario_f_overlapping_base_rotation_rejected(golden_setup):
    """
    Scenario F:
    Try overlapping base rotation (Alice 09:00-17:00, Bob 16:00-20:00) -> rejected.
    """
    schedule = golden_setup["schedule"]
    bob = golden_setup["bob"]

    with pytest.raises(RotationOverlapError):
        ScheduleRotation.objects.create(
            schedule=schedule,
            user=bob,
            start_time=datetime(2026, 9, 21, 16, 0, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2026, 9, 21, 20, 0, 0, tzinfo=dt_timezone.utc),
            is_override=False,
        )


@pytest.mark.django_db
def test_scenario_g_base_and_override_interplay(golden_setup):
    """
    Scenario G:
    Base: Alice 09:00-17:00
    Override: Bob 12:00-14:00
    Expected:
    13:00 -> Bob
    14:00 -> Alice
    """
    schedule = golden_setup["schedule"]
    alice = golden_setup["alice"]
    bob = golden_setup["bob"]

    ScheduleRotation.objects.create(
        schedule=schedule,
        user=bob,
        start_time=datetime(2026, 9, 21, 12, 0, 0, tzinfo=dt_timezone.utc),
        end_time=datetime(2026, 9, 21, 14, 0, 0, tzinfo=dt_timezone.utc),
        is_override=True,
    )

    t_1300 = datetime(2026, 9, 21, 13, 0, 0, tzinfo=dt_timezone.utc)
    t_1400 = datetime(2026, 9, 21, 14, 0, 0, tzinfo=dt_timezone.utc)

    assert get_on_call(schedule, t_1300) == bob
    assert get_on_call(schedule, t_1400) == alice
