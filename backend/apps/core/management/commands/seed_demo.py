"""Seed a believable demo org: 3 teams, 10 people, 6 services, 3 policies, 3 schedules and
60 days of incident history, plus a few incidents open right now.

    python manage.py seed_demo           # no-op if already seeded
    python manage.py seed_demo --reset   # wipe demo data and seed again (nightly on the demo)

Logins: admin@demo.local / demo1234 (team admin), responder@demo.local / demo1234.
The Payments policy uses 1-minute delays so a live alert visibly escalates in ~90 s.
"""

import random
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Membership, Team, User
from apps.alerting.actions import Event, ingest
from apps.alerting.models import Alert
from apps.catalog.models import Service
from apps.escalations.models import EscalationPolicy, EscalationRule, EscalationTarget
from apps.escalations.snapshot import build_snapshot
from apps.incidents import actions as incident_actions
from apps.incidents.models import EventType, Incident, IncidentEvent, Status, Urgency
from apps.schedules.models import (
    LayerMember,
    Rotation,
    Schedule,
    ScheduleLayer,
    ScheduleOverride,
)

PASSWORD = "demo1234"  # noqa: S105 -- public demo credential, documented in the README
TEAM_SLUGS = ("payments", "platform", "growth")
HISTORY_DAYS = 60

PEOPLE = [
    # email, name, timezone
    ("admin@demo.local", "Ada Okafor", "America/New_York"),
    ("responder@demo.local", "Riley Chen", "America/New_York"),
    ("viewer@demo.local", "Vic Ramos", "America/Chicago"),
    ("maya@demo.local", "Maya Patel", "Europe/London"),
    ("jonas@demo.local", "Jonas Berg", "Europe/Berlin"),
    ("sofia@demo.local", "Sofia Alvarez", "America/Los_Angeles"),
    ("kenji@demo.local", "Kenji Watanabe", "Asia/Tokyo"),
    ("lena@demo.local", "Lena Novak", "Europe/London"),
    ("omar@demo.local", "Omar Haddad", "Asia/Dubai"),
    ("priya@demo.local", "Priya Raman", "Asia/Kolkata"),
]

ALERT_TEXT = {
    "checkout-api": [
        "p99 latency above 2s on POST /checkout",
        "5xx rate above 3%",
        "Payment provider timeouts",
    ],
    "payments-worker": ["Queue depth above 10k", "Worker heartbeat missing", "Refund job failures"],
    "k8s-cluster": [
        "Node NotReady: ip-10-0-3-17",
        "Pod crash loop in ingress-nginx",
        "PVC 90% full on prometheus-0",
    ],
    "postgres-primary": [
        "Replication lag above 30s",
        "Connections above 90% of max",
        "Disk 92% full on pg-primary",
    ],
    "edge-cdn": ["Origin error rate above 1%", "TLS certificate expires in 7 days"],
    "signup-web": ["Signup conversion dropped 40%", "Frontend JS error spike"],
}


@dataclass
class Demo:
    users: dict[str, User]
    teams: dict[str, Team]
    services: dict[str, Service]


class Command(BaseCommand):
    help = "Seed demo data (idempotent). --reset wipes and re-seeds."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--reset", action="store_true", help="Delete demo data first")
        parser.add_argument("--seed", type=int, default=7, help="Random seed")

    def handle(self, *args: Any, **options: Any) -> None:
        if options["reset"]:
            self._wipe()
        elif Team.objects.filter(slug__in=TEAM_SLUGS).exists():
            self.stdout.write("Demo data already present; use --reset to re-seed.")
            return
        rng = random.Random(options["seed"])
        now = timezone.now()
        with transaction.atomic():
            demo = self._structure(now)
            count = self._history(demo, now, rng)
        # Live incidents go through the real pipeline (pages, ETA tasks) after commit.
        self._open_incidents(demo, now)
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(demo.teams)} teams, {len(demo.users)} users, "
                f"{len(demo.services)} services and {count} historical incidents.\n"
                f"Log in as admin@demo.local / {PASSWORD} or responder@demo.local / {PASSWORD}."
            )
        )

    # --- structure -------------------------------------------------------------------------

    def _wipe(self) -> None:
        Team.objects.filter(slug__in=TEAM_SLUGS).delete()
        User.objects.filter(email__in=[p[0] for p in PEOPLE]).delete()

    def _structure(self, now: datetime) -> Demo:
        users = {}
        for email, name, tz in PEOPLE:
            user = User.objects.create_user(email, PASSWORD, name=name, timezone=tz)
            users[email.split("@")[0]] = user
        u = users

        teams = {
            "payments": Team.objects.create(name="Payments", slug="payments"),
            "platform": Team.objects.create(name="Platform", slug="platform"),
            "growth": Team.objects.create(name="Growth", slug="growth"),
        }
        roster = {
            "payments": [
                ("admin", "admin"),
                ("responder", "responder"),
                ("maya", "responder"),
                ("jonas", "responder"),
                ("viewer", "viewer"),
            ],
            "platform": [
                ("admin", "admin"),
                ("responder", "responder"),
                ("kenji", "responder"),
                ("lena", "responder"),
                ("omar", "responder"),
                ("viewer", "viewer"),
            ],
            "growth": [
                ("sofia", "admin"),
                ("priya", "responder"),
                ("maya", "responder"),
                ("admin", "admin"),
                ("viewer", "viewer"),
            ],
        }
        for slug, members in roster.items():
            for key, role in members:
                Membership.objects.create(team=teams[slug], user=u[key], role=role)

        payments_sched = self._schedule(
            teams["payments"],
            "Payments primary",
            "America/New_York",
            layers=[
                (
                    "Weekday rotation",
                    Rotation.DAILY,
                    1,
                    None,
                    time(9),
                    [u["responder"], u["maya"], u["jonas"]],
                )
            ],
            now=now,
        )
        platform_sched = self._schedule(
            teams["platform"],
            "Platform follow-the-sun",
            "UTC",
            layers=[
                (
                    "Follow the sun (12h)",
                    Rotation.CUSTOM,
                    1,
                    timedelta(hours=12),
                    time(8),
                    [u["kenji"], u["lena"]],
                ),
                ("Backstop", Rotation.WEEKLY, 1, None, time(9), [u["omar"], u["responder"]]),
            ],
            now=now,
        )
        growth_sched = self._schedule(
            teams["growth"],
            "Growth weekly",
            "Europe/London",
            layers=[("Weekly", Rotation.WEEKLY, 1, None, time(10), [u["priya"], u["maya"]])],
            now=now,
        )
        # Overrides: one upcoming swap per schedule, so the timeline shows them.
        for schedule, who, offset_h in (
            (payments_sched, u["jonas"], 30),
            (platform_sched, u["omar"], 50),
            (growth_sched, u["sofia"], 72),
        ):
            start = (now + timedelta(hours=offset_h)).replace(minute=0, second=0, microsecond=0)
            ScheduleOverride.objects.create(
                schedule=schedule, user=who, start=start, end=start + timedelta(hours=6)
            )

        payments_policy = self._policy(
            teams["payments"],
            "Payments critical",
            loops=1,
            levels=[
                (1, [("schedule", payments_sched)]),
                (1, [("user", u["admin"])]),
                (5, [("user", u["maya"]), ("user", u["jonas"])]),
            ],
        )
        platform_policy = self._policy(
            teams["platform"],
            "Platform on-call",
            loops=0,
            levels=[(5, [("schedule", platform_sched)]), (15, [("user", u["admin"])])],
        )
        growth_policy = self._policy(
            teams["growth"],
            "Growth business hours",
            loops=0,
            levels=[(10, [("schedule", growth_sched)]), (30, [("user", u["sofia"])])],
        )

        def service(
            team: str,
            name: str,
            policy: EscalationPolicy,
            description: str,
            mode: str = Service.Mode.ACTIVE,
        ) -> Service:
            return Service.objects.create(
                team=teams[team],
                name=name,
                description=description,
                escalation_policy=policy,
                mode=mode,
            )

        services = {
            "checkout-api": service(
                "payments",
                "checkout-api",
                payments_policy,
                "Public checkout API behind the storefront.",
            ),
            "payments-worker": service(
                "payments",
                "payments-worker",
                payments_policy,
                "Async capture, refund and payout jobs.",
            ),
            "k8s-cluster": service(
                "platform",
                "k8s-cluster",
                platform_policy,
                "Production Kubernetes cluster (eu-west-1).",
            ),
            "postgres-primary": service(
                "platform", "postgres-primary", platform_policy, "Primary OLTP database."
            ),
            "edge-cdn": service("platform", "edge-cdn", platform_policy, "CDN and TLS edge."),
            "signup-web": service(
                "growth",
                "signup-web",
                growth_policy,
                "Signup funnel. In debug mode while alerts are tuned.",
                mode=Service.Mode.DEBUG,
            ),
        }
        return Demo(users=users, teams=teams, services=services)

    def _schedule(
        self, team: Team, name: str, tz: str, *, layers: list[tuple], now: datetime
    ) -> Schedule:
        schedule = Schedule.objects.create(team=team, name=name, timezone=tz)
        zone = ZoneInfo(tz)
        for index, (layer_name, rotation, turns, length, handoff, members) in enumerate(layers):
            # Start 30 days back on a handoff boundary: with 2 or 3 members (30 is divisible by
            # both) the first member listed is on call today — the demo responder sees their card.
            local_today = now.astimezone(zone)
            day = local_today.date() - timedelta(days=0 if local_today.time() >= handoff else 1)
            start = datetime.combine(day - timedelta(days=30), handoff, tzinfo=zone)
            layer = ScheduleLayer.objects.create(
                schedule=schedule,
                name=layer_name,
                priority=len(layers) - index,
                rotation_type=rotation,
                turn_count=turns,
                turn_length=length,
                start=start.astimezone(UTC),
                handoff_time=handoff,
            )
            for position, user in enumerate(members):
                LayerMember.objects.create(layer=layer, user=user, position=position)
        return schedule

    def _policy(
        self, team: Team, name: str, *, loops: int, levels: list[tuple]
    ) -> EscalationPolicy:
        policy = EscalationPolicy.objects.create(team=team, name=name, num_loops=loops)
        for level, (delay, targets) in enumerate(levels):
            rule = EscalationRule.objects.create(policy=policy, level=level, delay_minutes=delay)
            for position, (kind, target) in enumerate(targets):
                EscalationTarget.objects.create(
                    rule=rule,
                    position=position,
                    target_user=target if kind == "user" else None,
                    target_schedule=target if kind == "schedule" else None,
                )
        return policy

    # --- history ---------------------------------------------------------------------------

    def _history(self, demo: Demo, now: datetime, rng: random.Random) -> int:
        """Resolved incidents over the last 60 days with realistic, skewed response times."""
        noise = {
            "checkout-api": 2.2,
            "payments-worker": 1.4,
            "k8s-cluster": 1.8,
            "postgres-primary": 0.9,
            "edge-cdn": 0.6,
            "signup-web": 0.8,
        }
        responders = {
            name: list(
                User.objects.filter(
                    memberships__team=svc.team, memberships__role__in=["admin", "responder"]
                )
            )
            for name, svc in demo.services.items()
        }
        incidents: list[Incident] = []
        plans: list[dict[str, Any]] = []
        start_day = now - timedelta(days=HISTORY_DAYS)
        for day in range(HISTORY_DAYS):
            for name, svc in demo.services.items():
                weekend = (start_day + timedelta(days=day)).weekday() >= 5
                for _ in range(_poisson(rng, noise[name] * (0.6 if weekend else 1.0))):
                    triggered = start_day + timedelta(days=day, seconds=rng.randint(0, 86_399))
                    if triggered > now - timedelta(hours=2):
                        continue
                    plan = self._plan(rng, triggered)
                    who = rng.choice(responders[name])
                    incidents.append(
                        Incident(
                            service=svc,
                            title=rng.choice(ALERT_TEXT[name]),
                            status=Status.RESOLVED,
                            urgency=plan["urgency"],
                            assignee=who,
                            dedup_key=f"hist-{name}-{day}-{len(incidents)}",
                            escalation_snapshot=build_snapshot(svc.escalation_policy),
                            escalation_level=1 if plan["escalated"] else 0,
                            triggered_at=triggered,
                            first_response_at=plan["first"],
                            acknowledged_at=plan["ack"],
                            resolved_at=plan["resolved"],
                            alert_count=plan["alerts"],
                        )
                    )
                    plans.append({**plan, "who": who})
        Incident.objects.bulk_create(incidents, batch_size=500)

        alerts, events = [], []
        for incident, plan in zip(incidents, plans, strict=True):
            for i in range(plan["alerts"]):
                alerts.append(
                    Alert(
                        service=incident.service,
                        incident=incident,
                        dedup_key=incident.dedup_key,
                        severity="critical" if incident.urgency == Urgency.HIGH else "warning",
                        summary=incident.title,
                        source="prometheus",
                        status=Alert.Status.RESOLVED,
                        received_at=incident.triggered_at + timedelta(minutes=3 * i),
                    )
                )
            events.append(
                (
                    IncidentEvent(
                        incident=incident, type=EventType.TRIGGERED, message=incident.title
                    ),
                    incident.triggered_at,
                )
            )
            if plan["escalated"]:
                events.append(
                    (
                        IncidentEvent(
                            incident=incident,
                            type=EventType.ESCALATED,
                            message="Escalated to level 2",
                            data={"level": 1},
                        ),
                        incident.triggered_at + timedelta(minutes=1),
                    )
                )
            if plan["first"] and plan["first"] != plan["ack"]:
                # Someone triaged (reassigned) before anyone acknowledged: first response < MTTA.
                events.append(
                    (
                        IncidentEvent(
                            incident=incident,
                            type=EventType.REASSIGNED,
                            actor=plan["who"],
                            message=f"Reassigned to {plan['who']}",
                        ),
                        plan["first"],
                    )
                )
            if plan["ack"]:
                events.append(
                    (
                        IncidentEvent(
                            incident=incident,
                            type=EventType.ACKNOWLEDGED,
                            actor=plan["who"],
                            message="Acknowledged",
                        ),
                        plan["ack"],
                    )
                )
            events.append(
                (
                    IncidentEvent(
                        incident=incident,
                        type=EventType.RESOLVED,
                        actor=plan["who"] if plan["ack"] else None,
                        message="Resolved" if plan["ack"] else "Resolved by prometheus",
                    ),
                    plan["resolved"],
                )
            )
        Alert.objects.bulk_create(alerts, batch_size=1000)
        rows = IncidentEvent.objects.bulk_create([e for e, _ in events], batch_size=1000)
        # created_at is auto_now_add, so backdate it in a second pass.
        for row, (_, at) in zip(rows, events, strict=True):
            row.created_at = at
        IncidentEvent.objects.bulk_update(rows, ["created_at"], batch_size=1000)
        return len(incidents)

    @staticmethod
    def _plan(rng: random.Random, triggered: datetime) -> dict[str, Any]:
        urgency = Urgency.HIGH if rng.random() < 0.72 else Urgency.LOW
        source_resolved = rng.random() < 0.18  # flapping alerts that cleared on their own
        night = triggered.hour < 7 or triggered.hour >= 22
        ack_minutes = rng.lognormvariate(1.1 if urgency == Urgency.HIGH else 2.3, 0.7)
        ack_minutes *= 1.8 if night else 1.0
        escalated = urgency == Urgency.HIGH and ack_minutes > 1.0 and rng.random() < 0.45
        ack = None if source_resolved else triggered + timedelta(minutes=round(ack_minutes, 1))
        resolve_minutes = rng.lognormvariate(3.4, 0.8) + ack_minutes
        first = ack
        if ack and rng.random() < 0.35:
            first = triggered + timedelta(minutes=round(ack_minutes * rng.uniform(0.25, 0.7), 1))
        return {
            "urgency": urgency,
            "ack": ack,
            "first": first,
            "resolved": triggered + timedelta(minutes=round(resolve_minutes, 1)),
            "escalated": escalated and not source_resolved,
            "alerts": 1 + _poisson(rng, 1.3),
        }

    # --- right now ---------------------------------------------------------------------------

    def _open_incidents(self, demo: Demo, now: datetime) -> None:
        s, u = demo.services, demo.users
        ingest(
            s["k8s-cluster"],
            Event(
                action="trigger",
                dedup_key="node-notready-ip-10-0-3-17",
                summary="Node NotReady: ip-10-0-3-17",
                severity="critical",
                source="prometheus",
            ),
            now=now - timedelta(minutes=14),
        )
        acked = ingest(
            s["postgres-primary"],
            Event(
                action="trigger",
                dedup_key="pg-replication-lag",
                summary="Replication lag above 30s on pg-replica-2",
                severity="error",
                source="datadog",
            ),
            now=now - timedelta(minutes=42),
        )
        if acked.incident_id:
            incident_actions.acknowledge(
                acked.incident_id, actor=u["responder"], now=now - timedelta(minutes=38)
            )
            incident_actions.add_note(
                acked.incident_id,
                actor=u["responder"],
                text="Replica is catching up after the vacuum; watching.",
            )
        ingest(
            s["edge-cdn"],
            Event(
                action="trigger",
                dedup_key="tls-expiry-edge",
                summary="TLS certificate for cdn.example.com expires in 7 days",
                severity="warning",
                source="cert-monitor",
            ),
            now=now - timedelta(hours=3),
        )
        ingest(
            s["signup-web"],
            Event(
                action="trigger",
                dedup_key="signup-conversion",
                summary="Signup conversion dropped 40% in 1h",
                severity="critical",
                source="amplitude",
            ),
            now=now - timedelta(minutes=25),
        )
        self._backdate_timelines(now)

    @staticmethod
    def _backdate_timelines(now: datetime) -> None:
        """These incidents were opened "in the past" via ingest(now=...), but their timeline
        rows were stamped with the real clock. Move each event to the moment it describes."""
        for incident in Incident.objects.exclude(status=Status.RESOLVED).filter(
            service__team__slug__in=TEAM_SLUGS
        ):
            for event in incident.events.all():
                if event.type == EventType.ACKNOWLEDGED and incident.acknowledged_at:
                    at = incident.acknowledged_at
                elif event.type == EventType.NOTE_ADDED and incident.acknowledged_at:
                    at = incident.acknowledged_at + timedelta(minutes=2)
                else:
                    at = incident.triggered_at
                IncidentEvent.objects.filter(pk=event.pk).update(created_at=at)


def _poisson(rng: random.Random, lam: float) -> int:
    """Knuth's method; fine for the small rates used here."""
    limit, k, p = pow(2.718281828, -lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1
