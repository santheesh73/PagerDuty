import concurrent.futures

import pytest
from django.db import connection

from apps.alerts.models import Alert
from apps.alerts.triage import triage_alert
from apps.escalation.models import EscalationLevel, EscalationPolicy
from apps.escalation.tasks import check_and_escalate
from apps.incidents.exceptions import IncidentStateConflict
from apps.incidents.models import Incident, IncidentEvent
from apps.incidents.services import acknowledge_incident, resolve_incident
from apps.services.models import Service
from apps.users.models import Team, TeamMembership, User


@pytest.fixture
def race_setup(db):
    team = Team.objects.create(name="Race Team", slug="race-team")
    service = Service.objects.create(name="Race Service", slug="race-svc", team=team)
    user1 = User.objects.create_user(username="race_u1", email="u1@example.com")
    user2 = User.objects.create_user(username="race_u2", email="u2@example.com")
    user3 = User.objects.create_user(username="race_u3", email="u3@example.com")
    TeamMembership.objects.create(team=team, user=user1, role=TeamMembership.Role.RESPONDER, is_active=True)
    TeamMembership.objects.create(team=team, user=user2, role=TeamMembership.Role.RESPONDER, is_active=True)
    TeamMembership.objects.create(team=team, user=user3, role=TeamMembership.Role.RESPONDER, is_active=True)
    return {
        "team": team,
        "service": service,
        "user1": user1,
        "user2": user2,
        "user3": user3,
    }


@pytest.mark.django_db(transaction=True)
def test_high_concurrency_alert_ingestion_10_threads(race_setup):
    """
    Section 5: Alert Concurrency Attack.
    Simulate 10 identical alerts arriving concurrently for the same Service and fingerprint.
    Expected:
    - Exactly 1 unresolved Incident created.
    - All 10 alerts link to that same Incident.
    - Exactly 1 INCIDENT_TRIGGERED event, exactly 10 ALERT_ATTACHED events.
    - No unhandled IntegrityError or duplicate workflow initialization.
    """
    service = race_setup["service"]
    fingerprint = "race_fp_high_concurrency_10"
    alert_ids = []

    for i in range(10):
        a = Alert.objects.create(
            service=service,
            severity=Alert.Severity.CRITICAL,
            message=f"High concurrency error event {i}",
            source="cloudwatch",
            fingerprint=fingerprint,
        )
        alert_ids.append(a.id)

    def triage_worker(aid):
        connection.close()
        alert = Alert.objects.get(pk=aid)
        return triage_alert(alert)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(triage_worker, aid) for aid in alert_ids]
        results = [f.result() for f in futures]

    # All threads must return the exact same incident ID
    incident_ids = {r.id for r in results}
    assert len(incident_ids) == 1
    incident_id = incident_ids.pop()

    # Verify database state
    active_incidents = Incident.objects.filter(
        service=service,
        fingerprint=fingerprint,
        resolved_at__isnull=True,
    )
    assert active_incidents.count() == 1

    # Verify all 10 alerts are linked to the incident
    linked_alerts = Alert.objects.filter(incident_id=incident_id)
    assert linked_alerts.count() == 10

    # Verify timeline event counts
    inc = active_incidents.first()
    triggered_events = inc.events.filter(event_type=IncidentEvent.EventType.INCIDENT_TRIGGERED)
    attached_events = inc.events.filter(event_type=IncidentEvent.EventType.ALERT_ATTACHED)
    assert triggered_events.count() == 1
    assert attached_events.count() == 10


@pytest.mark.django_db(transaction=True)
def test_multi_user_simultaneous_acknowledgement_3_actors(race_setup):
    """
    Section 8: Simultaneous Acknowledgement Attack.
    Alice, Bob, and Charlie acknowledge the same TRIGGERED incident simultaneously.
    Expected:
    - First write wins: status becomes ACKNOWLEDGED.
    - Exactly 1 INCIDENT_ACKNOWLEDGED event recorded.
    - Exactly 1 acknowledged_at timestamp.
    - Exactly 1 authoritative actor recorded in the event.
    - Other requests become idempotent and harmless.
    """
    service = race_setup["service"]
    inc = Incident.objects.create(
        service=service,
        title="Simultaneous 3-way ACK test",
        severity=Incident.Severity.HIGH,
        fingerprint="ack_3way_fp",
        status=Incident.Status.TRIGGERED,
    )

    users = [race_setup["user1"], race_setup["user2"], race_setup["user3"]]

    def ack_worker(user_id):
        connection.close()
        user = User.objects.get(pk=user_id)
        incident = Incident.objects.get(pk=inc.pk)
        return acknowledge_incident(incident, user=user)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(ack_worker, u.id) for u in users]
        results = [f.result() for f in futures]

    for r in results:
        assert r.status == Incident.Status.ACKNOWLEDGED

    inc.refresh_from_db()
    assert inc.status == Incident.Status.ACKNOWLEDGED
    assert inc.acknowledged_at is not None

    # Verify exactly one INCIDENT_ACKNOWLEDGED event exists
    ack_events = list(inc.events.filter(event_type=IncidentEvent.EventType.INCIDENT_ACKNOWLEDGED))
    assert len(ack_events) == 1
    assert ack_events[0].actor_id in [u.id for u in users]


@pytest.mark.django_db(transaction=True)
def test_concurrent_acknowledge_and_resolve_race(race_setup):
    """
    Section 9: Acknowledge vs Resolve Race.
    Simulate Request A (acknowledge) and Request B (resolve) executing concurrently on a TRIGGERED incident.
    Expected:
    - Deterministic valid final state: status MUST be RESOLVED.
    - If acknowledge wins lock first: status -> ACK, then resolve -> RESOLVED.
      Both events exist in chronological order; acknowledged_at <= resolved_at.
    - If resolve wins lock first: status -> RESOLVED. Acknowledge then fails cleanly
      with IncidentStateConflict or no-ops, never overwriting resolved_at or setting
      acknowledged_at > resolved_at.
    """
    service = race_setup["service"]
    inc = Incident.objects.create(
        service=service,
        title="ACK vs Resolve Race",
        severity=Incident.Severity.CRITICAL,
        fingerprint="ack_vs_res_fp",
        status=Incident.Status.TRIGGERED,
    )

    u1 = race_setup["user1"]
    u2 = race_setup["user2"]

    def ack_worker():
        connection.close()
        try:
            incident = Incident.objects.get(pk=inc.pk)
            return acknowledge_incident(incident, user=u1), None
        except Exception as e:
            return None, e

    def res_worker():
        connection.close()
        try:
            incident = Incident.objects.get(pk=inc.pk)
            return resolve_incident(incident, user=u2), None
        except Exception as e:
            return None, e

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_ack = executor.submit(ack_worker)
        f_res = executor.submit(res_worker)
        res_ack, err_ack = f_ack.result()
        res_res, err_res = f_res.result()

    inc.refresh_from_db()
    # In all outcomes, final status MUST be RESOLVED
    assert inc.status == Incident.Status.RESOLVED
    assert inc.resolved_at is not None

    if inc.acknowledged_at is not None:
        # Acknowledge won lock first: acknowledged_at must be <= resolved_at
        assert inc.acknowledged_at <= inc.resolved_at
    else:
        # Resolve won lock first: acknowledge raised IncidentStateConflict
        assert isinstance(err_ack, IncidentStateConflict)


@pytest.mark.django_db(transaction=True)
def test_resolve_vs_escalation_race(race_setup):
    """
    Section 10: Resolve vs Escalation Race.
    Simulate Celery check_and_escalate and resolve_incident executing concurrently.
    Expected:
    - Never escalate after committed resolution.
    - If resolve wins lock: check_and_escalate sees status='RESOLVED' and halts cleanly.
    - If escalation wins lock: incident advances one level, and resolve then resolves it.
    - No duplicate notifications, no inconsistent level.
    """
    service = race_setup["service"]
    policy = EscalationPolicy.objects.create(
        name="Race Policy",
        slug="race-policy",
        team=race_setup["team"],
    )
    l1 = EscalationLevel.objects.create(
        policy=policy,
        order=1,
        wait_minutes=5,
        target_type=EscalationLevel.TargetType.USER,
        target_user=race_setup["user1"],
    )
    l2 = EscalationLevel.objects.create(
        policy=policy,
        order=2,
        wait_minutes=10,
        target_type=EscalationLevel.TargetType.USER,
        target_user=race_setup["user2"],
    )
    service.escalation_policy = policy
    service.save(update_fields=["escalation_policy"])

    inc = Incident.objects.create(
        service=service,
        title="Resolve vs Escalation Race",
        severity=Incident.Severity.CRITICAL,
        fingerprint="res_vs_esc_fp",
        status=Incident.Status.TRIGGERED,
        current_escalation_level=l1,
        assigned_user=race_setup["user1"],
        automation_generation=1,
    )

    def celery_worker():
        connection.close()
        # Direct execution of the task body under its own thread/connection
        return check_and_escalate(inc.id, expected_level_id=l1.id, expected_generation=1)

    def resolve_worker():
        connection.close()
        incident = Incident.objects.get(pk=inc.pk)
        return resolve_incident(incident, user=race_setup["user3"])

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_celery = executor.submit(celery_worker)
        f_resolve = executor.submit(resolve_worker)
        celery_ret = f_celery.result()
        assert f_resolve.result().status == Incident.Status.RESOLVED

    inc.refresh_from_db()
    # Final status MUST be RESOLVED
    assert inc.status == Incident.Status.RESOLVED

    # If celery_ret was False, it halted because resolve committed first
    # If celery_ret was True, it advanced to Level 2 before resolve committed
    if celery_ret:
        assert inc.current_escalation_level_id == l2.id
    else:
        assert inc.current_escalation_level_id == l1.id
