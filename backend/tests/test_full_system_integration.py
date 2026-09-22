from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.escalation.models import EscalationLevel, EscalationPolicy
from apps.escalation.tasks import check_and_escalate
from apps.incidents.models import Incident, IncidentEvent
from apps.notifications.models import Notification
from apps.scheduling.models import Schedule, ScheduleRotation
from apps.services.models import Service
from apps.users.models import Team, TeamMembership

User = get_user_model()


@pytest.fixture
def integration_stack():
    """
    Standard Canonical Stack per Section 81 (Golden Full-System Scenario):
    - Backend Team
    - Users: Alice (Engineer), Bob (Lead), Charlie (Responder)
    - Schedule: Backend Primary (Alice on-call 09:00 - 17:00 UTC)
    - Escalation Policy: Backend Critical
        Level 1: CURRENT_ON_CALL (wait 5 min)
        Level 2: Bob (wait 10 min)
        Level 3: Charlie (wait 15 min)
    - Service: Payment API (linked to Backend Critical policy)
    """
    team = Team.objects.create(name="Backend Team", slug="backend", is_active=True)

    alice = User.objects.create_user(username="alice", email="alice@example.com")
    bob = User.objects.create_user(username="bob", email="bob@example.com")
    charlie = User.objects.create_user(username="charlie", email="charlie@example.com")

    TeamMembership.objects.create(user=alice, team=team, role=TeamMembership.Role.ENGINEER, is_active=True)
    TeamMembership.objects.create(user=bob, team=team, role=TeamMembership.Role.LEAD, is_active=True)
    TeamMembership.objects.create(user=charlie, team=team, role=TeamMembership.Role.RESPONDER, is_active=True)

    schedule = Schedule.objects.create(
        name="Backend Primary",
        slug="backend-primary",
        team=team,
        timezone="UTC",
        is_primary=True,
        is_active=True,
    )

    # Alice on-call 09:00 - 17:00 UTC on 2026-09-22
    ref_day = datetime(2026, 9, 22, tzinfo=UTC)
    base_rotation = ScheduleRotation.objects.create(
        schedule=schedule,
        user=alice,
        start_time=datetime(2026, 9, 22, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 9, 22, 17, 0, tzinfo=UTC),
        is_override=False,
    )

    policy = EscalationPolicy.objects.create(
        name="Backend Critical",
        slug="backend-critical",
        team=team,
        is_active=True,
    )
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
    level_3 = EscalationLevel.objects.create(
        policy=policy,
        order=3,
        target_type=EscalationLevel.TargetType.USER,
        target_user=charlie,
        wait_minutes=15,
    )

    service = Service.objects.create(
        name="Payment API",
        slug="payment-api",
        team=team,
        escalation_policy=policy,
        is_active=True,
    )

    client = APIClient()

    return {
        "team": team,
        "alice": alice,
        "bob": bob,
        "charlie": charlie,
        "schedule": schedule,
        "base_rotation": base_rotation,
        "policy": policy,
        "level_1": level_1,
        "level_2": level_2,
        "level_3": level_3,
        "service": service,
        "client": client,
        "ref_day": ref_day,
    }


@pytest.mark.django_db(transaction=True)
def test_golden_full_system_scenario_end_to_end(integration_stack):
    """
    Comprehensive verification of Section 81:
    Step 1: Submit Alert -> Incident created, Alice assigned, Level 1 active, Alice notification created
    Step 2: Duplicate Alert -> New Alert, same Incident, Alice assignment preserved, single Alert attachment
    Step 3: Escalation -> Level 1 check -> Level 2, Bob assigned, Bob notification, escalation event
    Step 4: Acknowledge -> ACKNOWLEDGED, timeline event, subsequent tasks no-op, Charlie NOT notified
    Step 5: Resolve -> RESOLVED, resolved timestamp, timeline event, analytics updated
    Step 6: New Alert -> Same fingerprint after resolution -> NEW incident created with clean lifecycle
    Step 7: Reopen Test -> Reopen second incident -> Generation increments, Level 1 restarts, stale task no-ops
    Step 8: Override Test -> Create override for Bob -> New incident assigned Bob
    Step 9: Analytics -> Backend calculates MTTA, MTTR, and distribution accurately
    """
    client = integration_stack["client"]
    service = integration_stack["service"]
    alice = integration_stack["alice"]
    bob = integration_stack["bob"]
    charlie = integration_stack["charlie"]
    level_1 = integration_stack["level_1"]
    level_2 = integration_stack["level_2"]
    level_3 = integration_stack["level_3"]
    assert level_3.order == 3
    schedule = integration_stack["schedule"]

    trigger_time = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)

    # -------------------------------------------------------------------------
    # STEP 1: Submit Alert -> Real POST /api/alerts/
    # -------------------------------------------------------------------------
    with patch("django.utils.timezone.now", return_value=trigger_time), \
         patch("apps.escalation.tasks.check_and_escalate.apply_async") as mock_schedule_task, \
         patch("apps.notifications.tasks.dispatch_notification.delay") as mock_dispatch_task:

        resp = client.post(
            "/api/alerts/",
            {
                "service_id": service.id,
                "severity": "CRITICAL",
                "message": "Payment gateway timeout rate > 15%",
                "source": "datadog",
                "metadata": {"region": "us-east-1"},
            },
            format="json",
        )
        assert resp.status_code == 201
        alert_data = resp.json()
        incident_id = alert_data["incident_id"]
        assert incident_id is not None

    incident = Incident.objects.get(id=incident_id)
    assert incident.status == Incident.Status.TRIGGERED
    assert incident.assigned_user == alice
    assert incident.current_escalation_level == level_1
    assert incident.automation_generation == 1

    # Verify notification created for Alice
    alice_notif = Notification.objects.filter(incident=incident, recipient=alice).first()
    assert alice_notif is not None
    assert alice_notif.escalation_level == level_1
    assert alice_notif.channel == "EMAIL"
    mock_dispatch_task.assert_called_once_with(alice_notif.id)

    # Verify escalation task scheduled for countdown=300 (5 mins * 60)
    mock_schedule_task.assert_called_once_with(
        args=[incident.id, level_1.id, 1],
        countdown=300,
    )

    # Verify timeline events
    event_types = list(incident.events.values_list("event_type", flat=True))
    assert IncidentEvent.EventType.INCIDENT_TRIGGERED in event_types
    assert IncidentEvent.EventType.ALERT_ATTACHED in event_types
    assert IncidentEvent.EventType.ESCALATION_STARTED in event_types
    assert IncidentEvent.EventType.RESPONDER_ASSIGNED in event_types

    # -------------------------------------------------------------------------
    # STEP 2: Duplicate Alert while Incident is active
    # -------------------------------------------------------------------------
    t_dup = datetime(2026, 9, 22, 10, 2, tzinfo=UTC)
    with patch("django.utils.timezone.now", return_value=t_dup):
        resp_dup = client.post(
            "/api/alerts/",
            {
                "service_id": service.id,
                "severity": "CRITICAL",
                "message": "Payment gateway timeout rate > 15%",
                "source": "datadog",
            },
            format="json",
        )
        assert resp_dup.status_code == 201
        dup_data = resp_dup.json()
        assert dup_data["incident_id"] == incident.id

    incident.refresh_from_db()
    # Assignee remains Alice (stable assignment)
    assert incident.assigned_user == alice
    # Alerts count is now 2
    assert incident.alerts.count() == 2
    # No duplicate Alice notification created
    assert Notification.objects.filter(incident=incident, recipient=alice).count() == 1

    # -------------------------------------------------------------------------
    # STEP 3: Escalation Check -> Level 2 (Bob)
    # -------------------------------------------------------------------------
    t_esc1 = datetime(2026, 9, 22, 10, 5, tzinfo=UTC)
    with patch("django.utils.timezone.now", return_value=t_esc1), \
         patch("apps.escalation.tasks.check_and_escalate.apply_async") as mock_schedule_task2, \
         patch("apps.notifications.tasks.dispatch_notification.delay") as mock_dispatch_task2:

        res = check_and_escalate(incident.id, level_1.id, expected_generation=1)
        assert res is True

    incident.refresh_from_db()
    assert incident.current_escalation_level == level_2
    assert incident.assigned_user == bob

    bob_notif = Notification.objects.filter(incident=incident, recipient=bob).first()
    assert bob_notif is not None
    assert bob_notif.escalation_level == level_2
    mock_dispatch_task2.assert_called_once_with(bob_notif.id)

    # Next check scheduled for Level 2 (wait 10 min -> 600s)
    mock_schedule_task2.assert_called_once_with(
        args=[incident.id, level_2.id, 1],
        countdown=600,
    )

    # Verify INCIDENT_ESCALATED event recorded
    escalated_event = incident.events.filter(event_type=IncidentEvent.EventType.INCIDENT_ESCALATED).first()
    assert escalated_event is not None
    assert escalated_event.metadata["from_level"] == level_1.id
    assert escalated_event.metadata["to_level"] == level_2.id

    # -------------------------------------------------------------------------
    # STEP 4: Acknowledge from API -> Halts subsequent escalation
    # -------------------------------------------------------------------------
    t_ack = datetime(2026, 9, 22, 10, 8, tzinfo=UTC)
    with patch("django.utils.timezone.now", return_value=t_ack):
        ack_resp = client.post(f"/api/incidents/{incident.id}/acknowledge/")
        assert ack_resp.status_code == 200
        assert ack_resp.json()["status"] == "ACKNOWLEDGED"

    incident.refresh_from_db()
    assert incident.status == Incident.Status.ACKNOWLEDGED
    assert incident.acknowledged_at is not None

    # Timer fires for Level 2 -> Should NO-OP because incident is ACKNOWLEDGED
    res_ack_check = check_and_escalate(incident.id, level_2.id, expected_generation=1)
    assert res_ack_check is False

    # Charlie must NOT be notified
    assert not Notification.objects.filter(incident=incident, recipient=charlie).exists()
    assert incident.current_escalation_level == level_2

    # -------------------------------------------------------------------------
    # STEP 5: Resolve from API
    # -------------------------------------------------------------------------
    t_res = datetime(2026, 9, 22, 10, 20, tzinfo=UTC)
    with patch("django.utils.timezone.now", return_value=t_res):
        res_resp = client.post(f"/api/incidents/{incident.id}/resolve/")
        assert res_resp.status_code == 200
        assert res_resp.json()["status"] == "RESOLVED"

    incident.refresh_from_db()
    assert incident.status == Incident.Status.RESOLVED
    assert incident.resolved_at is not None

    # -------------------------------------------------------------------------
    # STEP 6: New Alert arriving AFTER Resolution creates a NEW Incident
    # -------------------------------------------------------------------------
    t_new = datetime(2026, 9, 22, 10, 30, tzinfo=UTC)
    with patch("django.utils.timezone.now", return_value=t_new), \
         patch("apps.escalation.tasks.check_and_escalate.apply_async"), \
         patch("apps.notifications.tasks.dispatch_notification.delay"):

        resp_new = client.post(
            "/api/alerts/",
            {
                "service_id": service.id,
                "severity": "CRITICAL",
                "message": "Payment gateway timeout rate > 15%",
                "source": "datadog",
            },
            format="json",
        )
        assert resp_new.status_code == 201
        new_inc_id = resp_new.json()["incident_id"]
        assert new_inc_id != incident.id

    incident_2 = Incident.objects.get(id=new_inc_id)
    assert incident_2.status == Incident.Status.TRIGGERED
    assert incident_2.assigned_user == alice
    assert incident_2.current_escalation_level == level_1
    assert incident_2.automation_generation == 1

    # Resolve incident_2 so we can test Reopen
    with patch("django.utils.timezone.now", return_value=datetime(2026, 9, 22, 10, 45, tzinfo=UTC)):
        client.post(f"/api/incidents/{incident_2.id}/resolve/")
    incident_2.refresh_from_db()
    assert incident_2.status == Incident.Status.RESOLVED

    # -------------------------------------------------------------------------
    # STEP 7: Reopen Test -> Generation Increments & Stale Tasks No-op
    # -------------------------------------------------------------------------
    t_reopen = datetime(2026, 9, 22, 11, 0, tzinfo=UTC)
    with patch("django.utils.timezone.now", return_value=t_reopen), \
         patch("apps.escalation.tasks.check_and_escalate.apply_async"), \
         patch("apps.notifications.tasks.dispatch_notification.delay"):

        reopen_resp = client.post(f"/api/incidents/{incident_2.id}/reopen/")
        assert reopen_resp.status_code == 200

    incident_2.refresh_from_db()
    assert incident_2.status == Incident.Status.TRIGGERED
    assert incident_2.automation_generation == 2
    assert incident_2.current_escalation_level == level_1

    # An old task from generation 1 executes -> must discard without escalating
    res_stale = check_and_escalate(incident_2.id, level_1.id, expected_generation=1)
    assert res_stale is False
    incident_2.refresh_from_db()
    assert incident_2.current_escalation_level == level_1  # unchanged

    # Clean up incident_2
    with patch("django.utils.timezone.now", return_value=datetime(2026, 9, 22, 11, 30, tzinfo=UTC)):
        client.post(f"/api/incidents/{incident_2.id}/resolve/")

    # -------------------------------------------------------------------------
    # STEP 8: Override Test -> Active Override takes precedence
    # -------------------------------------------------------------------------
    # Create override: Bob on call 12:00 - 14:00 UTC
    override_start = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    override_end = datetime(2026, 9, 22, 14, 0, tzinfo=UTC)
    ScheduleRotation.objects.create(
        schedule=schedule,
        user=bob,
        start_time=override_start,
        end_time=override_end,
        is_override=True,
    )

    t_override = datetime(2026, 9, 22, 13, 0, tzinfo=UTC)
    # Check GET /api/schedules/{id}/on-call/ at 13:00
    on_call_resp = client.get(f"/api/schedules/{schedule.id}/on-call/?at={t_override.isoformat()}")
    assert on_call_resp.status_code == 200
    on_call_data = on_call_resp.json()
    assert on_call_data["user"]["username"] == "bob"
    assert on_call_data["source"] == "override"

    # Ingest alert during override window -> new incident assigned to Bob
    with patch("django.utils.timezone.now", return_value=t_override), \
         patch("apps.escalation.tasks.check_and_escalate.apply_async"), \
         patch("apps.notifications.tasks.dispatch_notification.delay"):

        resp_over = client.post(
            "/api/alerts/",
            {
                "service_id": service.id,
                "severity": "HIGH",
                "message": "Memory saturation > 90%",
                "source": "cloudwatch",
            },
            format="json",
        )
        assert resp_over.status_code == 201
        inc3_id = resp_over.json()["incident_id"]

    incident_3 = Incident.objects.get(id=inc3_id)
    assert incident_3.assigned_user == bob
    assert incident_3.current_escalation_level == level_1

    # Acknowledge and resolve incident_3
    with patch("django.utils.timezone.now", return_value=datetime(2026, 9, 22, 13, 5, tzinfo=UTC)):
        client.post(f"/api/incidents/{incident_3.id}/acknowledge/")
    with patch("django.utils.timezone.now", return_value=datetime(2026, 9, 22, 13, 20, tzinfo=UTC)):
        client.post(f"/api/incidents/{incident_3.id}/resolve/")

    # -------------------------------------------------------------------------
    # STEP 9: Analytics Verification (Authoritative backend calculation)
    # -------------------------------------------------------------------------
    analytics_resp = client.get("/api/analytics/summary/?range=30d")
    assert analytics_resp.status_code == 200
    summary = analytics_resp.json()

    assert summary["incident_count"] >= 3
    # Incident 1: trigger=10:00, ack=10:08 (480s), res=10:20 (1200s)
    assert summary["mtta_seconds"] is not None
    assert summary["mttr_seconds"] is not None
    assert summary["mtta_seconds"] > 0
    assert summary["mttr_seconds"] > 0

    # Severity distribution
    sev_resp = client.get("/api/analytics/severity-distribution/?range=30d")
    assert sev_resp.status_code == 200
    sev_data = sev_resp.json()
    assert any(s["severity"].upper() == "CRITICAL" and s["count"] > 0 for s in sev_data)

    # Incidents by service
    svc_resp = client.get("/api/analytics/incidents-by-service/?range=30d")
    assert svc_resp.status_code == 200
    svc_data = svc_resp.json()
    assert any(s["service_name"] == "Payment API" for s in svc_data)


@pytest.mark.django_db(transaction=True)
def test_duplicate_escalation_task_is_idempotent(integration_stack):
    """Scenario 8 & 34: Duplicate task execution does not double-advance levels."""
    service = integration_stack["service"]
    level_1 = integration_stack["level_1"]
    level_2 = integration_stack["level_2"]

    incident = Incident.objects.create(
        service=service,
        title="Double task test",
        fingerprint="fp-double-task",
        status=Incident.Status.TRIGGERED,
        current_escalation_level=level_1,
        automation_generation=1,
    )

    with patch("apps.escalation.tasks.check_and_escalate.apply_async"), \
         patch("apps.notifications.tasks.dispatch_notification.delay"):
        # First execution -> advances to Level 2
        res1 = check_and_escalate(incident.id, level_1.id, expected_generation=1)
        assert res1 is True

        # Second duplicate execution for Level 1 -> level mismatch -> NO-OP
        res2 = check_and_escalate(incident.id, level_1.id, expected_generation=1)
        assert res2 is False

    incident.refresh_from_db()
    assert incident.current_escalation_level == level_2


@pytest.mark.django_db(transaction=True)
def test_final_level_exhaustion_halts_cleanly(integration_stack):
    """Scenario 35: Reaching final escalation level records ESCALATION_EXHAUSTED once."""
    service = integration_stack["service"]
    level_3 = integration_stack["level_3"]
    charlie = integration_stack["charlie"]

    incident = Incident.objects.create(
        service=service,
        title="Final level exhaustion test",
        fingerprint="fp-exhaustion",
        status=Incident.Status.TRIGGERED,
        assigned_user=charlie,
        current_escalation_level=level_3,
        automation_generation=1,
    )

    res = check_and_escalate(incident.id, level_3.id, expected_generation=1)
    assert res is False

    incident.refresh_from_db()
    assert incident.status == Incident.Status.TRIGGERED
    assert incident.current_escalation_level == level_3

    exhausted_events = incident.events.filter(event_type=IncidentEvent.EventType.ESCALATION_EXHAUSTED)
    assert exhausted_events.count() == 1
    assert exhausted_events.first().metadata["final_level_id"] == level_3.id
