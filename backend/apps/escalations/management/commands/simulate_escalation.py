"""Walk one alert through two escalation levels with simulated time, then roll back.

    python manage.py simulate_escalation

Everything runs in a transaction that is rolled back, so it's safe against any database.
Time is passed explicitly to the engine (no sleeping, no Celery), which is exactly how the
test suite drives it.
"""

from datetime import UTC, datetime, time, timedelta
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Membership, Team, User
from apps.alerting.actions import Event, ingest
from apps.catalog.models import Service
from apps.escalations import engine
from apps.escalations.models import EscalationPolicy, EscalationRule, EscalationTarget
from apps.incidents.models import Incident
from apps.schedules.models import LayerMember, Rotation, Schedule, ScheduleLayer


class _Rollback(Exception):
    pass


class Command(BaseCommand):
    help = "Simulate an alert escalating through two levels under frozen time (rolled back)."

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            with transaction.atomic():
                self._simulate()
                raise _Rollback
        except _Rollback:
            self.stdout.write(self.style.SUCCESS("\nSimulation rolled back; no data kept."))

    def _simulate(self) -> None:
        t0 = datetime(2026, 1, 7, 12, 0, tzinfo=UTC)
        team = Team.objects.create(name="Simulation", slug="simulation-walkthrough")
        ana, ben, cleo = (
            User.objects.create_user(f"{n.lower()}@sim.invalid", None, name=n)
            for n in ("Ana", "Ben", "Cleo")
        )
        for user in (ana, ben, cleo):
            Membership.objects.create(team=team, user=user)
        schedule = Schedule.objects.create(team=team, name="Primary on-call")
        layer = ScheduleLayer.objects.create(
            schedule=schedule,
            name="Daily",
            rotation_type=Rotation.DAILY,
            start=t0 - timedelta(days=2),
            handoff_time=time(9, 0),
        )
        LayerMember.objects.create(layer=layer, user=ana, position=0)
        policy = EscalationPolicy.objects.create(team=team, name="Sim policy")
        levels: list[tuple[int, dict[str, Any]]] = [
            (5, {"target_schedule": schedule}),
            (10, {"target_user": ben}),
            (15, {"target_user": cleo}),
        ]
        for level, (delay, target) in enumerate(levels):
            rule = EscalationRule.objects.create(policy=policy, level=level, delay_minutes=delay)
            EscalationTarget.objects.create(rule=rule, **target)
        service = Service.objects.create(team=team, name="checkout-sim", escalation_policy=policy)

        result = ingest(
            service,
            Event(
                action="trigger",
                dedup_key="cpu-high",
                summary="CPU above 95% on checkout-sim",
                severity="critical",
                source="simulation",
            ),
            now=t0,
        )
        assert result.incident_id is not None
        incident = Incident.objects.get(pk=result.incident_id)
        self._show(incident, t0, "alert received")

        for minutes in (5, 15):
            now = t0 + timedelta(minutes=minutes)
            incident.refresh_from_db()
            engine.escalate(incident.pk, incident.escalation_level, incident.escalation_loop, now)
            incident.refresh_from_db()
            self._show(incident, now, "timer expired")

        if incident.escalation_level != 2:
            raise AssertionError("expected the incident to reach level 3")
        self.stdout.write("\nTimeline:")
        for event in incident.events.order_by("id"):
            self.stdout.write(f"  {event.type:<16} {event.message}")

    def _show(self, incident: Incident, now: datetime, why: str) -> None:
        due = incident.next_escalation_at
        self.stdout.write(
            f"[{now:%H:%M}] {why:<15} level {incident.escalation_level + 1}  "
            f"assignee={incident.assignee}  next escalation="
            f"{due.strftime('%H:%M') if due else '—'}"
        )
