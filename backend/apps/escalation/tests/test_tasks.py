from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.escalation.models import EscalationLevel, EscalationPolicy
from apps.escalation.tasks import check_and_escalate
from apps.incidents.models import Incident, IncidentEvent
from apps.incidents.services import acknowledge_incident, resolve_incident
from apps.notifications.models import Notification
from apps.services.models import Service
from apps.users.models import Team, TeamMembership

User = get_user_model()


@pytest.fixture
def task_env():
    team = Team.objects.create(name="Task Team", slug="task-team")
    user_alice = User.objects.create_user(username="alice_t", email="alice_t@example.com")
    user_bob = User.objects.create_user(username="bob_t", email="bob_t@example.com")

    TeamMembership.objects.create(user=user_alice, team=team, role=TeamMembership.Role.ENGINEER)
    TeamMembership.objects.create(user=user_bob, team=team, role=TeamMembership.Role.LEAD)

    policy = EscalationPolicy.objects.create(name="Task Policy", slug="task-policy", team=team)
    level_1 = EscalationLevel.objects.create(
        policy=policy,
        order=1,
        target_type=EscalationLevel.TargetType.USER,
        target_user=user_alice,
        wait_minutes=5,
    )
    level_2 = EscalationLevel.objects.create(
        policy=policy,
        order=2,
        target_type=EscalationLevel.TargetType.USER,
        target_user=user_bob,
        wait_minutes=10,
    )

    service = Service.objects.create(name="Task Service", slug="task-svc", team=team, escalation_policy=policy)

    incident = Incident.objects.create(
        service=service,
        title="Task Test Incident",
        fingerprint="fp-task-1",
        status=Incident.Status.TRIGGERED,
        assigned_user=user_alice,
        current_escalation_level=level_1,
        automation_generation=1,
    )

    return {
        "incident": incident,
        "alice": user_alice,
        "bob": user_bob,
        "level_1": level_1,
        "level_2": level_2,
    }


@pytest.mark.django_db
def test_acknowledged_incident_stops_escalation_noop(task_env):
    incident = task_env["incident"]
    acknowledge_incident(incident, task_env["alice"])
    incident.refresh_from_db()
    assert incident.status == Incident.Status.ACKNOWLEDGED

    with patch("apps.notifications.tasks.dispatch_notification.delay") as mock_dispatch:
        res = check_and_escalate(incident.id, task_env["level_1"].id, incident.automation_generation)
        assert res is False
        mock_dispatch.assert_not_called()

    incident.refresh_from_db()
    assert incident.current_escalation_level == task_env["level_1"]
    assert incident.assigned_user == task_env["alice"]
    # No Bob notification created
    assert not Notification.objects.filter(recipient=task_env["bob"]).exists()


@pytest.mark.django_db
def test_resolved_incident_stops_escalation_noop(task_env):
    incident = task_env["incident"]
    resolve_incident(incident, task_env["alice"])
    incident.refresh_from_db()
    assert incident.status == Incident.Status.RESOLVED

    with patch("apps.notifications.tasks.dispatch_notification.delay") as mock_dispatch:
        res = check_and_escalate(incident.id, task_env["level_1"].id, incident.automation_generation)
        assert res is False
        mock_dispatch.assert_not_called()

    incident.refresh_from_db()
    assert incident.current_escalation_level == task_env["level_1"]
    assert incident.assigned_user == task_env["alice"]
    assert not Notification.objects.filter(recipient=task_env["bob"]).exists()


@pytest.mark.django_db
def test_stale_task_with_outdated_generation_noop(task_env):
    incident = task_env["incident"]
    # Simulate reopen: automation_generation is bumped to 2
    incident.automation_generation = 2
    incident.save()

    with patch("apps.notifications.tasks.dispatch_notification.delay") as mock_dispatch:
        # Task queued with older generation 1 executes
        res = check_and_escalate(incident.id, task_env["level_1"].id, expected_generation=1)
        assert res is False
        mock_dispatch.assert_not_called()

    incident.refresh_from_db()
    assert incident.current_escalation_level == task_env["level_1"]
    assert incident.assigned_user == task_env["alice"]
    assert not Notification.objects.filter(recipient=task_env["bob"]).exists()


@pytest.mark.django_db
def test_mismatched_expected_level_noop(task_env):
    incident = task_env["incident"]
    # Task expects Level 999 which does not match current_escalation_level (Level 1)
    with patch("apps.notifications.tasks.dispatch_notification.delay") as mock_dispatch:
        res = check_and_escalate(incident.id, expected_level_id=999, expected_generation=incident.automation_generation)
        assert res is False
        mock_dispatch.assert_not_called()

    incident.refresh_from_db()
    assert incident.current_escalation_level == task_env["level_1"]


@pytest.mark.django_db
def test_missing_incident_noop():
    res = check_and_escalate(incident_id=999999, expected_level_id=1, expected_generation=1)
    assert res is False
