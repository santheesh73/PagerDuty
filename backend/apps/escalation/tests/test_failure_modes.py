
import pytest
from django.db.models.deletion import ProtectedError

from apps.escalation.models import EscalationLevel, EscalationPolicy
from apps.escalation.tasks import check_and_escalate
from apps.incidents.models import Incident, IncidentEvent
from apps.incidents.services import reopen_incident, resolve_incident
from apps.notifications.models import Notification
from apps.services.models import Service
from apps.users.models import Team, TeamMembership, User


@pytest.fixture
def failure_mode_setup(db):
    team = Team.objects.create(name="Esc Failure Team", slug="esc-failure-team")
    user1 = User.objects.create_user(username="esc_u1", email="u1@example.com")
    user2 = User.objects.create_user(username="esc_u2", email="u2@example.com")
    user3 = User.objects.create_user(username="esc_u3", email="u3@example.com")
    TeamMembership.objects.create(team=team, user=user1, role=TeamMembership.Role.RESPONDER, is_active=True)
    TeamMembership.objects.create(team=team, user=user2, role=TeamMembership.Role.RESPONDER, is_active=True)
    TeamMembership.objects.create(team=team, user=user3, role=TeamMembership.Role.RESPONDER, is_active=True)

    policy = EscalationPolicy.objects.create(name="Failure Policy", slug="failure-policy", team=team)
    level1 = EscalationLevel.objects.create(
        policy=policy,
        order=1,
        wait_minutes=5,
        target_type=EscalationLevel.TargetType.USER,
        target_user=user1,
    )
    level2 = EscalationLevel.objects.create(
        policy=policy,
        order=2,
        wait_minutes=10,
        target_type=EscalationLevel.TargetType.USER,
        target_user=user2,
    )
    level3 = EscalationLevel.objects.create(
        policy=policy,
        order=3,
        wait_minutes=15,
        target_type=EscalationLevel.TargetType.USER,
        target_user=user3,
    )

    service = Service.objects.create(
        name="Failure Service",
        slug="failure-svc",
        team=team,
        escalation_policy=policy,
    )

    incident = Incident.objects.create(
        service=service,
        title="Escalation failure mode test",
        severity=Incident.Severity.HIGH,
        fingerprint="failure_fp",
        status=Incident.Status.TRIGGERED,
        current_escalation_level=level1,
        assigned_user=user1,
        automation_generation=1,
    )

    return {
        "team": team,
        "users": [user1, user2, user3],
        "policy": policy,
        "levels": [level1, level2, level3],
        "service": service,
        "incident": incident,
    }


@pytest.mark.django_db
def test_duplicate_celery_execution_stress_10_executions(failure_mode_setup):
    """
    Section 12: Duplicate Celery Execution Stress.
    Simulate running check_and_escalate 10 times consecutively with identical parameters.
    Expected:
    - First run: succeeds and advances from Level 1 to Level 2.
    - Subsequent 9 runs: expected_level_id=level1 does not match current level2 -> all NO-OP.
    - Exactly 1 level transition occurred (current level is 2, not 3).
    - Exactly 1 INCIDENT_ESCALATED event.
    - Exactly 1 notification created for Level 2.
    """
    inc = failure_mode_setup["incident"]
    l1 = failure_mode_setup["levels"][0]
    l2 = failure_mode_setup["levels"][1]

    results = []
    for _ in range(10):
        res = check_and_escalate(inc.id, expected_level_id=l1.id, expected_generation=1)
        results.append(res)

    assert results[0] is True
    for subsequent in results[1:]:
        assert subsequent is False

    inc.refresh_from_db()
    assert inc.current_escalation_level_id == l2.id
    assert inc.assigned_user == failure_mode_setup["users"][1]

    escalated_events = inc.events.filter(event_type=IncidentEvent.EventType.INCIDENT_ESCALATED)
    assert escalated_events.count() == 1

    notifications_l2 = Notification.objects.filter(incident=inc, escalation_level=l2)
    assert notifications_l2.count() == 1


@pytest.mark.django_db
def test_task_execution_after_resolution_all_noop(failure_mode_setup):
    """
    Section 14: Task Execution After Resolution.
    Queue multiple tasks, resolve incident, then execute all tasks.
    Expected:
    - All tasks return False / no-op immediately.
    - No escalation, no reassignment, no notification.
    """
    inc = failure_mode_setup["incident"]
    l1 = failure_mode_setup["levels"][0]

    resolve_incident(inc, user=failure_mode_setup["users"][2])
    inc.refresh_from_db()
    assert inc.status == Incident.Status.RESOLVED

    for _ in range(5):
        res = check_and_escalate(inc.id, expected_level_id=l1.id, expected_generation=1)
        assert res is False

    inc.refresh_from_db()
    assert inc.status == Incident.Status.RESOLVED
    assert inc.current_escalation_level_id == l1.id


@pytest.mark.django_db
def test_stale_generation_attack(failure_mode_setup):
    """
    Section 15: Stale Generation Attack.
    Lifecycle:
    - Generation 1 active.
    - Incident resolved, then reopened -> automation_generation becomes 2.
    - Execute stale Generation 1 tasks.
    Expected:
    - Stale generation 1 task discarded / returns False.
    - Current generation 2 workflow untouched.
    """
    inc = failure_mode_setup["incident"]
    l1 = failure_mode_setup["levels"][0]

    resolve_incident(inc, user=failure_mode_setup["users"][0])
    reopen_incident(inc, user=failure_mode_setup["users"][0])
    inc.refresh_from_db()
    assert inc.automation_generation == 2
    assert inc.status == Incident.Status.TRIGGERED

    # Execute stale generation 1 task
    stale_result = check_and_escalate(inc.id, expected_level_id=l1.id, expected_generation=1)
    assert stale_result is False

    inc.refresh_from_db()
    assert inc.automation_generation == 2


@pytest.mark.django_db
def test_multiple_reopen_cycles_generation_monotonically_increases(failure_mode_setup):
    """
    Section 16: Multiple Reopen Cycles.
    Trigger -> Resolve -> Reopen -> Resolve -> Reopen -> Resolve -> Reopen (3 cycles).
    Expected:
    - automation_generation increases monotonically: 1 -> 2 -> 3 -> 4.
    - Stale tasks from each previous generation (1, 2, 3) all cleanly no-op.
    """
    inc = failure_mode_setup["incident"]
    l1 = failure_mode_setup["levels"][0]
    user = failure_mode_setup["users"][0]

    for expected_gen in [2, 3, 4]:
        resolve_incident(inc, user=user)
        reopen_incident(inc, user=user)
        inc.refresh_from_db()
        assert inc.automation_generation == expected_gen

    # Now verify tasks from older generations all no-op
    for old_gen in [1, 2, 3]:
        res = check_and_escalate(inc.id, expected_level_id=l1.id, expected_generation=old_gen)
        assert res is False

    # Valid task for current generation 4 executes properly
    res_valid = check_and_escalate(inc.id, expected_level_id=l1.id, expected_generation=4)
    assert res_valid is True
    inc.refresh_from_db()
    assert inc.current_escalation_level_id == failure_mode_setup["levels"][1].id


@pytest.mark.django_db
def test_missing_next_level_halts_cleanly_with_escalation_exhausted(db):
    """
    Section 34: Missing Next Level.
    Escalation policy configured with only 1 level.
    When check_and_escalate executes:
    - Discovers no next level exists.
    - Records ESCALATION_EXHAUSTED timeline event exactly once.
    - Incident remains TRIGGERED.
    - No IndexError or uncaught exception.
    """
    team = Team.objects.create(name="Single Level Team", slug="single-lvl-team")
    user = User.objects.create_user(username="single_user")
    TeamMembership.objects.create(team=team, user=user, role=TeamMembership.Role.RESPONDER, is_active=True)

    policy = EscalationPolicy.objects.create(name="Single Policy", slug="single-policy", team=team)
    level1 = EscalationLevel.objects.create(
        policy=policy,
        order=1,
        wait_minutes=5,
        target_type=EscalationLevel.TargetType.USER,
        target_user=user,
    )
    service = Service.objects.create(name="Single Svc", slug="single-svc", team=team, escalation_policy=policy)
    inc = Incident.objects.create(
        service=service,
        title="Single level exhaustion test",
        severity=Incident.Severity.MEDIUM,
        fingerprint="single_fp",
        status=Incident.Status.TRIGGERED,
        current_escalation_level=level1,
        assigned_user=user,
        automation_generation=1,
    )

    res = check_and_escalate(inc.id, expected_level_id=level1.id, expected_generation=1)
    assert res is False

    inc.refresh_from_db()
    assert inc.status == Incident.Status.TRIGGERED
    exhausted_events = inc.events.filter(event_type=IncidentEvent.EventType.ESCALATION_EXHAUSTED)
    assert exhausted_events.count() == 1


@pytest.mark.django_db
def test_policy_and_level_deletion_protected_from_cascade(failure_mode_setup):
    """
    Section 32 & 33: Policy & Escalation Level Deletion Hardening.
    Attempting to delete a policy linked to a Service or an EscalationLevel linked to an active Incident
    must be prevented by on_delete=PROTECT.
    """
    policy = failure_mode_setup["policy"]
    level1 = failure_mode_setup["levels"][0]

    # Deleting policy referenced by service raises ProtectedError
    with pytest.raises(ProtectedError):
        policy.delete()

    # Deleting level referenced by incident raises ProtectedError
    with pytest.raises(ProtectedError):
        level1.delete()
