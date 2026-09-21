from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.alerts.models import Alert
from apps.alerts.triage import triage_alert
from apps.escalation.models import EscalationLevel, EscalationPolicy
from apps.escalation.tasks import check_and_escalate
from apps.incidents.models import Incident, IncidentEvent
from apps.incidents.services import acknowledge_incident, reopen_incident, resolve_incident
from apps.notifications.models import Notification
from apps.notifications.providers import SimulatedEmailProvider
from apps.notifications.tasks import dispatch_notification
from apps.scheduling.models import Schedule, ScheduleRotation
from apps.services.models import Service
from apps.users.models import Team, TeamMembership

User = get_user_model()


@pytest.fixture
def acceptance_stack():
    """
    Standard Canonical Stack per Section 69:
    - Backend Team
    - Users: Alice, Bob, Charlie
    - Schedule: Alice on-call at trigger time
    - Service: Payment API
    - Policy:
        Level 1: CURRENT_ON_CALL (wait 1 min)
        Level 2: Bob (wait 1 min)
        Level 3: Charlie (final)
    """
    team = Team.objects.create(name="Backend Team", slug="backend")

    alice = User.objects.create_user(username="alice", email="alice@example.com")
    bob = User.objects.create_user(username="bob", email="bob@example.com")
    charlie = User.objects.create_user(username="charlie", email="charlie@example.com")

    TeamMembership.objects.create(user=alice, team=team, role=TeamMembership.Role.ENGINEER)
    TeamMembership.objects.create(user=bob, team=team, role=TeamMembership.Role.LEAD)
    TeamMembership.objects.create(user=charlie, team=team, role=TeamMembership.Role.LEAD)

    schedule = Schedule.objects.create(
        name="Backend Primary",
        slug="backend-primary",
        team=team,
        is_primary=True,
        is_active=True,
    )

    ref_date = datetime(2026, 9, 21, tzinfo=dt_timezone.utc)
    ScheduleRotation.objects.create(
        schedule=schedule,
        user=alice,
        start_time=datetime(2026, 9, 21, 9, 0, tzinfo=dt_timezone.utc),
        end_time=datetime(2026, 9, 21, 17, 0, tzinfo=dt_timezone.utc),
        is_override=False,
    )

    policy = EscalationPolicy.objects.create(
        name="Backend Critical Policy",
        slug="backend-critical-policy",
        team=team,
        is_active=True,
    )
    level_1 = EscalationLevel.objects.create(
        policy=policy,
        order=1,
        target_type=EscalationLevel.TargetType.CURRENT_ON_CALL,
        wait_minutes=1,
    )
    level_2 = EscalationLevel.objects.create(
        policy=policy,
        order=2,
        target_type=EscalationLevel.TargetType.USER,
        target_user=bob,
        wait_minutes=1,
    )
    level_3 = EscalationLevel.objects.create(
        policy=policy,
        order=3,
        target_type=EscalationLevel.TargetType.USER,
        target_user=charlie,
        wait_minutes=0,
    )

    service = Service.objects.create(
        name="Payment API",
        slug="payment-api",
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
        "level_3": level_3,
        "service": service,
    }


@pytest.mark.django_db(transaction=True)
def test_scenario_a_submit_alert_triggers_incident_and_pages_level_1(acceptance_stack):
    """
    Scenario A: Submit Alert -> Incident created (TRIGGERED), Level 1 active,
    Alice assigned, Alice Notification created/dispatched, escalation check scheduled.
    """
    trigger_ts = datetime(2026, 9, 21, 10, 0, tzinfo=dt_timezone.utc)

    with patch("django.utils.timezone.now", return_value=trigger_ts), \
         patch("apps.escalation.tasks.check_and_escalate.apply_async") as mock_escalation_task, \
         patch("apps.notifications.tasks.dispatch_notification.delay") as mock_dispatch_task:
        alert = Alert.objects.create(
            service=acceptance_stack["service"],
            source="datadog",
            message="500 Internal Server Error rate > 5%",
            severity=Alert.Severity.CRITICAL,
            fingerprint="fp-acceptance-a",
        )
        incident = triage_alert(alert)

    assert incident.status == Incident.Status.TRIGGERED
    assert incident.current_escalation_level == acceptance_stack["level_1"]
    assert incident.assigned_user == acceptance_stack["alice"]

    # Verify notification created
    notif = Notification.objects.get(incident=incident, recipient=acceptance_stack["alice"])
    assert notif.escalation_level == acceptance_stack["level_1"]
    assert notif.channel == "EMAIL"

    # Verify escalation task scheduled with countdown=60s (wait_minutes=1)
    mock_escalation_task.assert_called_once_with(
        args=[incident.id, acceptance_stack["level_1"].id, incident.automation_generation],
        countdown=60,
    )


@pytest.mark.django_db(transaction=True)
def test_scenario_b_unacknowledged_incident_escalates_to_level_2(acceptance_stack):
    """
    Scenario B: Do not acknowledge -> Level 1 check executes ->
    Level 2 active, Bob assigned, Bob notified, INCIDENT_ESCALATED event recorded.
    """
    incident = Incident.objects.create(
        service=acceptance_stack["service"],
        title="Payment API Latency Spike",
        fingerprint="fp-acceptance-b",
        status=Incident.Status.TRIGGERED,
        assigned_user=acceptance_stack["alice"],
        current_escalation_level=acceptance_stack["level_1"],
    )

    with patch("apps.escalation.tasks.check_and_escalate.apply_async") as mock_escalation_task, \
         patch("apps.notifications.tasks.dispatch_notification.delay") as mock_dispatch_task:
        res = check_and_escalate(incident.id, acceptance_stack["level_1"].id, incident.automation_generation)
        assert res is True

    incident.refresh_from_db()
    assert incident.current_escalation_level == acceptance_stack["level_2"]
    assert incident.assigned_user == acceptance_stack["bob"]

    # Bob notified
    bob_notif = Notification.objects.get(incident=incident, recipient=acceptance_stack["bob"])
    assert bob_notif.escalation_level == acceptance_stack["level_2"]

    # INCIDENT_ESCALATED event
    event = incident.events.get(event_type=IncidentEvent.EventType.INCIDENT_ESCALATED)
    assert event.metadata["from_order"] == 1
    assert event.metadata["to_order"] == 2
    assert event.metadata["new_user_id"] == acceptance_stack["bob"].id

    # Level 2 check scheduled
    mock_escalation_task.assert_called_once_with(
        args=[incident.id, acceptance_stack["level_2"].id, incident.automation_generation],
        countdown=60,
    )


@pytest.mark.django_db(transaction=True)
def test_scenario_c_acknowledge_before_level_2_check_halts_escalation(acceptance_stack):
    """
    Scenario C: Acknowledge before Level 2 check -> status ACKNOWLEDGED ->
    when Level 2 delayed task executes: NO-OP, Charlie NOT notified.
    """
    incident = Incident.objects.create(
        service=acceptance_stack["service"],
        title="Database Deadlock",
        fingerprint="fp-acceptance-c",
        status=Incident.Status.TRIGGERED,
        assigned_user=acceptance_stack["bob"],
        current_escalation_level=acceptance_stack["level_2"],
    )

    # Bob acknowledges incident at 10:03
    acknowledge_incident(incident, acceptance_stack["bob"])
    incident.refresh_from_db()
    assert incident.status == Incident.Status.ACKNOWLEDGED

    # Delayed Level 2 task executes at 10:05
    with patch("apps.notifications.tasks.dispatch_notification.delay") as mock_dispatch:
        res = check_and_escalate(incident.id, acceptance_stack["level_2"].id, incident.automation_generation)
        assert res is False
        mock_dispatch.assert_not_called()

    incident.refresh_from_db()
    # Current level remains 2; Charlie is never notified; status remains ACKNOWLEDGED
    assert incident.current_escalation_level == acceptance_stack["level_2"]
    assert incident.status == Incident.Status.ACKNOWLEDGED
    assert not Notification.objects.filter(incident=incident, recipient=acceptance_stack["charlie"]).exists()


@pytest.mark.django_db(transaction=True)
def test_scenario_d_resolve_stops_escalation(acceptance_stack):
    """
    Scenario D: Resolve Incident -> status RESOLVED -> subsequent check executes -> NO-OP.
    """
    incident = Incident.objects.create(
        service=acceptance_stack["service"],
        title="Network blip",
        fingerprint="fp-acceptance-d",
        status=Incident.Status.TRIGGERED,
        assigned_user=acceptance_stack["bob"],
        current_escalation_level=acceptance_stack["level_2"],
    )
    resolve_incident(incident, acceptance_stack["bob"])
    incident.refresh_from_db()
    assert incident.status == Incident.Status.RESOLVED

    with patch("apps.notifications.tasks.dispatch_notification.delay") as mock_dispatch:
        res = check_and_escalate(incident.id, acceptance_stack["level_2"].id, incident.automation_generation)
        assert res is False
        mock_dispatch.assert_not_called()

    incident.refresh_from_db()
    assert incident.status == Incident.Status.RESOLVED
    assert not Notification.objects.filter(incident=incident, recipient=acceptance_stack["charlie"]).exists()


@pytest.mark.django_db(transaction=True)
def test_scenario_e_acknowledge_before_first_timer_prevents_bob_notification(acceptance_stack):
    """
    Scenario E: Create another incident, acknowledge before first timer ->
    Alice notified once, Bob never notified.
    """
    t_1000 = datetime(2026, 9, 21, 10, 0, tzinfo=dt_timezone.utc)
    with patch("django.utils.timezone.now", return_value=t_1000):
        alert = Alert.objects.create(
            service=acceptance_stack["service"],
            source="pagerduty-test",
            message="Minor cache miss spike",
            severity=Alert.Severity.LOW,
            fingerprint="fp-acceptance-e",
        )
        incident = triage_alert(alert)
    assert incident.assigned_user == acceptance_stack["alice"]

    # Alice acknowledges immediately
    acknowledge_incident(incident, acceptance_stack["alice"])
    incident.refresh_from_db()

    # Level 1 timer fires
    res = check_and_escalate(incident.id, acceptance_stack["level_1"].id, incident.automation_generation)
    assert res is False

    # Verify: Alice has 1 notification, Bob has 0
    assert Notification.objects.filter(incident=incident, recipient=acceptance_stack["alice"]).count() == 1
    assert Notification.objects.filter(incident=incident, recipient=acceptance_stack["bob"]).count() == 0


@pytest.mark.django_db(transaction=True)
def test_scenario_f_duplicate_level_1_task_execution(acceptance_stack):
    """
    Scenario F: Duplicate Level 1 task -> executed twice -> exactly one transition to Level 2.
    """
    incident = Incident.objects.create(
        service=acceptance_stack["service"],
        title="Duplicate Task Test",
        fingerprint="fp-acceptance-f",
        status=Incident.Status.TRIGGERED,
        assigned_user=acceptance_stack["alice"],
        current_escalation_level=acceptance_stack["level_1"],
    )

    with patch("apps.escalation.tasks.check_and_escalate.apply_async"), \
         patch("apps.notifications.tasks.dispatch_notification.delay"):
        # Run 1
        res1 = check_and_escalate(incident.id, acceptance_stack["level_1"].id, incident.automation_generation)
        assert res1 is True

        # Run 2 (duplicate execution of the same Level 1 check)
        res2 = check_and_escalate(incident.id, acceptance_stack["level_1"].id, incident.automation_generation)
        assert res2 is False

    incident.refresh_from_db()
    assert incident.current_escalation_level == acceptance_stack["level_2"]
    assert incident.assigned_user == acceptance_stack["bob"]

    # Exactly one Bob notification and one INCIDENT_ESCALATED event
    assert Notification.objects.filter(incident=incident, recipient=acceptance_stack["bob"]).count() == 1
    assert incident.events.filter(event_type=IncidentEvent.EventType.INCIDENT_ESCALATED).count() == 1


@pytest.mark.django_db(transaction=True)
def test_scenario_g_notification_retry_same_row(acceptance_stack):
    """
    Scenario G: Notification retry -> simulate failure once ->
    same Notification retried, attempt_count increments, eventual delivery SENT,
    no duplicate Notification row.
    """
    incident = Incident.objects.create(
        service=acceptance_stack["service"],
        title="Retry Scenario",
        fingerprint="fp-acceptance-g",
    )
    notif = Notification.objects.create(
        incident=incident,
        recipient=acceptance_stack["alice"],
        dedupe_key="dedupe-g-1",
    )

    # 1. Force simulated failure on attempt 1
    SimulatedEmailProvider.force_failure = True
    try:
        from celery.exceptions import Retry
        with patch.object(dispatch_notification, "retry", side_effect=Retry("retry-exception")):
            with pytest.raises(Retry):
                dispatch_notification(notif.id)
    finally:
        SimulatedEmailProvider.force_failure = False

    notif.refresh_from_db()
    assert notif.attempt_count == 1
    assert notif.status == Notification.Status.PENDING
    assert "Simulated email delivery failed" in notif.last_error

    # 2. Retry attempt succeeds
    dispatch_notification(notif.id)

    notif.refresh_from_db()
    assert notif.attempt_count == 2
    assert notif.status == Notification.Status.SENT
    assert notif.sent_at is not None
    # No duplicate Notification rows created
    assert Notification.objects.filter(incident=incident).count() == 1


@pytest.mark.django_db(transaction=True)
def test_scenario_h_resolve_then_reopen_stale_tasks_noop(acceptance_stack):
    """
    Scenario H: Resolve then reopen -> new automation_generation (2),
    Level 1 restarts, old tasks from previous generation NO-OP.
    """
    incident = Incident.objects.create(
        service=acceptance_stack["service"],
        title="Lifecycle Reopen Scenario",
        fingerprint="fp-acceptance-h",
        status=Incident.Status.TRIGGERED,
        assigned_user=acceptance_stack["alice"],
        current_escalation_level=acceptance_stack["level_1"],
        automation_generation=1,
    )

    # 1. Resolve incident in Generation 1
    resolve_incident(incident, acceptance_stack["alice"])
    incident.refresh_from_db()
    assert incident.status == Incident.Status.RESOLVED

    # 2. Reopen incident -> generation becomes 2, Level 1 restarts
    with patch("apps.escalation.tasks.check_and_escalate.apply_async"), \
         patch("apps.notifications.tasks.dispatch_notification.delay"):
        reopened = reopen_incident(incident, acceptance_stack["alice"])
        assert reopened.status == Incident.Status.TRIGGERED
        assert reopened.automation_generation == 2
        assert reopened.current_escalation_level == acceptance_stack["level_1"]

    # 3. Old generation 1 task wakes up -> NO-OP due to generation mismatch!
    with patch("apps.notifications.tasks.dispatch_notification.delay") as mock_dispatch:
        res = check_and_escalate(reopened.id, acceptance_stack["level_1"].id, expected_generation=1)
        assert res is False
        mock_dispatch.assert_not_called()

    reopened.refresh_from_db()
    assert reopened.current_escalation_level == acceptance_stack["level_1"]

    # 4. New generation 2 task runs -> successfully escalates to Level 2!
    with patch("apps.escalation.tasks.check_and_escalate.apply_async"), \
         patch("apps.notifications.tasks.dispatch_notification.delay"):
        res_gen2 = check_and_escalate(reopened.id, acceptance_stack["level_1"].id, expected_generation=2)
        assert res_gen2 is True

    reopened.refresh_from_db()
    assert reopened.current_escalation_level == acceptance_stack["level_2"]
    assert reopened.assigned_user == acceptance_stack["bob"]
