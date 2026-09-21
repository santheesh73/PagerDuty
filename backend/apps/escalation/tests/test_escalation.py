from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.escalation.models import EscalationLevel, EscalationPolicy
from apps.escalation.services import start_incident_escalation
from apps.escalation.tasks import check_and_escalate
from apps.incidents.models import Incident, IncidentEvent
from apps.notifications.models import Notification
from apps.scheduling.models import Schedule, ScheduleRotation
from apps.services.models import Service
from apps.users.models import Team, TeamMembership

User = get_user_model()


@pytest.fixture
def escalation_env():
    team = Team.objects.create(name="Core Backend", slug="core-backend")
    alice = User.objects.create_user(username="alice_esc", email="alice_esc@example.com")
    bob = User.objects.create_user(username="bob_esc", email="bob_esc@example.com")
    charlie = User.objects.create_user(username="charlie_esc", email="charlie_esc@example.com")

    TeamMembership.objects.create(user=alice, team=team, role=TeamMembership.Role.ENGINEER)
    TeamMembership.objects.create(user=bob, team=team, role=TeamMembership.Role.LEAD)
    TeamMembership.objects.create(user=charlie, team=team, role=TeamMembership.Role.LEAD)

    schedule = Schedule.objects.create(name="Primary Schedule", slug="backend-sched", team=team, is_primary=True, is_active=True)

    # Alice on call 09:00 - 17:00, Bob on call 17:00 - 01:00 on 2026-09-21
    ref_day = datetime(2026, 9, 21, tzinfo=dt_timezone.utc)
    ScheduleRotation.objects.create(
        schedule=schedule,
        user=alice,
        start_time=datetime(2026, 9, 21, 9, 0, tzinfo=dt_timezone.utc),
        end_time=datetime(2026, 9, 21, 17, 0, tzinfo=dt_timezone.utc),
        is_override=False,
    )
    ScheduleRotation.objects.create(
        schedule=schedule,
        user=bob,
        start_time=datetime(2026, 9, 21, 17, 0, tzinfo=dt_timezone.utc),
        end_time=datetime(2026, 9, 22, 1, 0, tzinfo=dt_timezone.utc),
        is_override=False,
    )

    policy = EscalationPolicy.objects.create(name="2-Tier Policy", slug="two-tier-policy", team=team, is_active=True)
    level_1 = EscalationLevel.objects.create(
        policy=policy,
        order=1,
        target_type=EscalationLevel.TargetType.CURRENT_ON_CALL,
        wait_minutes=5,
    )
    level_2 = EscalationLevel.objects.create(
        policy=policy,
        order=2,
        target_type=EscalationLevel.TargetType.USER,
        target_user=bob,
        wait_minutes=10,
    )

    service = Service.objects.create(
        name="Orders Service",
        slug="orders-service",
        team=team,
        escalation_policy=policy,
    )

    return {
        "team": team,
        "alice": alice,
        "bob": bob,
        "charlie": charlie,
        "schedule": schedule,
        "policy": policy,
        "level_1": level_1,
        "level_2": level_2,
        "service": service,
    }


@pytest.mark.django_db
def test_initial_automation_starts_level_1_and_assigns_on_call(escalation_env):
    trigger_time = datetime(2026, 9, 21, 10, 0, tzinfo=dt_timezone.utc)
    incident = Incident.objects.create(
        service=escalation_env["service"],
        title="High CPU on Orders",
        fingerprint="fp-orders-cpu",
        status=Incident.Status.TRIGGERED,
        triggered_at=trigger_time,
    )

    with patch("apps.escalation.tasks.check_and_escalate.apply_async") as mock_schedule, \
         patch("apps.notifications.tasks.dispatch_notification.delay") as mock_dispatch:
        started = start_incident_escalation(incident, trigger_time)
        assert started is True

    incident.refresh_from_db()
    assert incident.current_escalation_level == escalation_env["level_1"]
    assert incident.assigned_user == escalation_env["alice"]

    # Verify notification created
    notif = Notification.objects.filter(incident=incident, recipient=escalation_env["alice"]).first()
    assert notif is not None
    assert notif.escalation_level == escalation_env["level_1"]
    assert notif.status == Notification.Status.PENDING

    # Verify timeline events
    events = list(incident.events.order_by("created_at"))
    event_types = [e.event_type for e in events]
    assert IncidentEvent.EventType.ESCALATION_STARTED in event_types
    assert IncidentEvent.EventType.RESPONDER_ASSIGNED in event_types


@pytest.mark.django_db
def test_normal_escalation_advances_level_1_to_level_2(escalation_env):
    trigger_time = datetime(2026, 9, 21, 10, 0, tzinfo=dt_timezone.utc)
    incident = Incident.objects.create(
        service=escalation_env["service"],
        title="Payment gateway timeout",
        fingerprint="fp-timeout",
        status=Incident.Status.TRIGGERED,
        assigned_user=escalation_env["alice"],
        current_escalation_level=escalation_env["level_1"],
        triggered_at=trigger_time,
    )

    with patch("apps.escalation.tasks.check_and_escalate.apply_async") as mock_schedule, \
         patch("apps.notifications.tasks.dispatch_notification.delay") as mock_dispatch:
        res = check_and_escalate(incident.id, escalation_env["level_1"].id, incident.automation_generation)
        assert res is True

    incident.refresh_from_db()
    assert incident.current_escalation_level == escalation_env["level_2"]
    assert incident.assigned_user == escalation_env["bob"]

    # Verify Bob notification created
    bob_notif = Notification.objects.filter(incident=incident, recipient=escalation_env["bob"]).first()
    assert bob_notif is not None
    assert bob_notif.escalation_level == escalation_env["level_2"]

    # Verify INCIDENT_ESCALATED event
    escalated_event = incident.events.filter(event_type=IncidentEvent.EventType.INCIDENT_ESCALATED).first()
    assert escalated_event is not None
    assert escalated_event.metadata["from_level"] == escalation_env["level_1"].id
    assert escalated_event.metadata["to_level"] == escalation_env["level_2"].id
    assert escalated_event.metadata["new_user_id"] == escalation_env["bob"].id


@pytest.mark.django_db
def test_final_level_exhaustion_records_event_and_halts(escalation_env):
    incident = Incident.objects.create(
        service=escalation_env["service"],
        title="Unrecoverable database failure",
        fingerprint="fp-db-fail",
        status=Incident.Status.TRIGGERED,
        assigned_user=escalation_env["bob"],
        current_escalation_level=escalation_env["level_2"],
    )

    with patch("apps.escalation.tasks.check_and_escalate.apply_async") as mock_schedule:
        res = check_and_escalate(incident.id, escalation_env["level_2"].id, incident.automation_generation)
        assert res is False

    incident.refresh_from_db()
    # Level and status remain unchanged
    assert incident.current_escalation_level == escalation_env["level_2"]
    assert incident.status == Incident.Status.TRIGGERED

    # Verify ESCALATION_EXHAUSTED event recorded
    exhausted_event = incident.events.filter(event_type=IncidentEvent.EventType.ESCALATION_EXHAUSTED).first()
    assert exhausted_event is not None
    assert exhausted_event.metadata["final_level_id"] == escalation_env["level_2"].id


@pytest.mark.django_db
def test_target_changes_with_schedule_on_current_on_call(escalation_env):
    # Level 2 is configured as CURRENT_ON_CALL
    level_2 = escalation_env["level_2"]
    level_2.target_type = EscalationLevel.TargetType.CURRENT_ON_CALL
    level_2.target_user = None
    level_2.save()

    incident = Incident.objects.create(
        service=escalation_env["service"],
        title="Service degraded",
        fingerprint="fp-degraded",
        status=Incident.Status.TRIGGERED,
        assigned_user=escalation_env["alice"],
        current_escalation_level=escalation_env["level_1"],
    )

    # Advance escalation at 18:00 (when Bob is on call according to schedule)
    with patch("django.utils.timezone.now") as mock_now, \
         patch("apps.escalation.tasks.check_and_escalate.apply_async"), \
         patch("apps.notifications.tasks.dispatch_notification.delay"):
        mock_now.return_value = datetime(2026, 9, 21, 18, 0, tzinfo=dt_timezone.utc)
        res = check_and_escalate(incident.id, escalation_env["level_1"].id, incident.automation_generation)
        assert res is True

    incident.refresh_from_db()
    assert incident.current_escalation_level == level_2
    assert incident.assigned_user == escalation_env["bob"]
