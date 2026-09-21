from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from apps.escalation.models import EscalationLevel, EscalationPolicy
from apps.escalation.tasks import check_and_escalate
from apps.incidents.models import Incident, IncidentEvent
from apps.incidents.services import reopen_incident, resolve_incident
from apps.notifications.models import Notification
from apps.services.models import Service
from apps.users.models import Team, TeamMembership

User = get_user_model()


@pytest.fixture
def idem_env():
    team = Team.objects.create(name="Idem Team", slug="idem-team")
    alice = User.objects.create_user(username="alice_i", email="alice_i@example.com")
    bob = User.objects.create_user(username="bob_i", email="bob_i@example.com")
    charlie = User.objects.create_user(username="charlie_i", email="charlie_i@example.com")

    TeamMembership.objects.create(user=alice, team=team, role=TeamMembership.Role.ENGINEER)
    TeamMembership.objects.create(user=bob, team=team, role=TeamMembership.Role.LEAD)
    TeamMembership.objects.create(user=charlie, team=team, role=TeamMembership.Role.LEAD)

    policy = EscalationPolicy.objects.create(name="Idem Policy", slug="idem-policy", team=team)
    level_1 = EscalationLevel.objects.create(
        policy=policy,
        order=1,
        target_type=EscalationLevel.TargetType.USER,
        target_user=alice,
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
        wait_minutes=0,
    )

    service = Service.objects.create(name="Idem Service", slug="idem-svc", team=team, escalation_policy=policy)

    incident = Incident.objects.create(
        service=service,
        title="Idempotency Incident",
        fingerprint="fp-idem-1",
        status=Incident.Status.TRIGGERED,
        assigned_user=alice,
        current_escalation_level=level_1,
        automation_generation=1,
    )

    return {
        "incident": incident,
        "alice": alice,
        "bob": bob,
        "charlie": charlie,
        "level_1": level_1,
        "level_2": level_2,
        "level_3": level_3,
    }


@pytest.mark.django_db
def test_duplicate_task_execution_only_advances_once(idem_env):
    incident = idem_env["incident"]

    with patch("apps.escalation.tasks.check_and_escalate.apply_async"), \
         patch("apps.notifications.tasks.dispatch_notification.delay"):
        # First execution advances 1 -> 2
        res1 = check_and_escalate(incident.id, idem_env["level_1"].id, incident.automation_generation)
        assert res1 is True

        # Second duplicate execution with same expected_level_id=1 runs
        res2 = check_and_escalate(incident.id, idem_env["level_1"].id, incident.automation_generation)
        assert res2 is False

    incident.refresh_from_db()
    # Level must remain 2, not skip to 3!
    assert incident.current_escalation_level == idem_env["level_2"]
    assert incident.assigned_user == idem_env["bob"]

    # Bob should only have one notification
    bob_notifs = Notification.objects.filter(incident=incident, recipient=idem_env["bob"])
    assert bob_notifs.count() == 1

    # Exactly one INCIDENT_ESCALATED event
    escalated_events = incident.events.filter(event_type=IncidentEvent.EventType.INCIDENT_ESCALATED)
    assert escalated_events.count() == 1


@pytest.mark.django_db
def test_duplicate_escalation_exhausted_event_prevented(idem_env):
    incident = idem_env["incident"]
    incident.current_escalation_level = idem_env["level_3"]
    incident.assigned_user = idem_env["charlie"]
    incident.save()

    # Call check_and_escalate on the final level twice
    res1 = check_and_escalate(incident.id, idem_env["level_3"].id, incident.automation_generation)
    assert res1 is False

    res2 = check_and_escalate(incident.id, idem_env["level_3"].id, incident.automation_generation)
    assert res2 is False

    exhausted_events = incident.events.filter(event_type=IncidentEvent.EventType.ESCALATION_EXHAUSTED)
    assert exhausted_events.count() == 1


@pytest.mark.django_db
def test_reopen_increments_generation_and_invalidates_stale_tasks(idem_env):
    incident = idem_env["incident"]
    # 1. Resolve incident in Generation 1
    resolve_incident(incident, idem_env["alice"])
    incident.refresh_from_db()
    assert incident.status == Incident.Status.RESOLVED

    # 2. Reopen incident -> generation bumps to 2, restarts escalation at Level 1
    with patch("apps.escalation.tasks.check_and_escalate.apply_async"), \
         patch("apps.notifications.tasks.dispatch_notification.delay"):
        reopened = reopen_incident(incident, idem_env["alice"])
        assert reopened.status == Incident.Status.TRIGGERED
        assert reopened.automation_generation == 2
        assert reopened.current_escalation_level == idem_env["level_1"]

    # 3. An old Generation 1 task fires now
    with patch("apps.notifications.tasks.dispatch_notification.delay") as mock_dispatch:
        res = check_and_escalate(reopened.id, expected_level_id=idem_env["level_1"].id, expected_generation=1)
        assert res is False
        mock_dispatch.assert_not_called()

    reopened.refresh_from_db()
    # Still at Level 1, not prematurely advanced
    assert reopened.current_escalation_level == idem_env["level_1"]

    # 4. A valid Generation 2 task fires -> advances successfully!
    with patch("apps.escalation.tasks.check_and_escalate.apply_async"), \
         patch("apps.notifications.tasks.dispatch_notification.delay"):
        res2 = check_and_escalate(reopened.id, expected_level_id=idem_env["level_1"].id, expected_generation=2)
        assert res2 is True

    reopened.refresh_from_db()
    assert reopened.current_escalation_level == idem_env["level_2"]
