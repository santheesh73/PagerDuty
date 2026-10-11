"""A seeded, deterministic fault-injection simulator for the paging pipeline.

It builds a random org (teams, schedules with overlapping overrides, policies of varying
depth and loop counts, services), then runs a long random sequence of real operations —
ingest with colliding dedup keys, human actions, worker and sweeper runs on a virtual
clock — while injecting faults:

    broker_down      enqueueing raises (dispatch.on_commit must swallow it)
    message_lost     a task message silently disappears
    message_dup      a task message is delivered twice
    crash            an action raises mid-transaction after writing pages
    concurrent_sweep two sweepers race over the same due set (real threads)
    clock_skew       a sweep runs with the clock jittered by up to ±90 s
    policy_edit      a live policy is rewritten while incidents escalate
    mode_flip        a service switches to debug/maintenance/active mid-flight
    channel_failure  email/SMS delivery raises (retried with backoff, then fails)

Some simulated people have personal notification plans (SMS now, a call after 2-5 minutes, a
webhook...). Those add two checks to every send: a later step never goes out before its time
(I19), and never after the incident was acknowledged or resolved (I18, C1).

After every operation it checks every database-checkable invariant (apps/core/invariants.py)
plus the ones only an observer can see: each Notification is sent at most once (I4), due
incidents advance or clear on a sweep (I7), each operation writes the expected number of
timeline events (I10), first_response_at never changes once set (I9), debug never sends
(I12), snapshots never change (I17), and no page goes out for a resolved incident (C1).
At the end it drains the system and checks nothing is left pending (I5) or ticking (I6).

The same seed always produces the same run. Real code paths are exercised; only the broker
(Celery's apply_async), the email channel and the clock are simulated.
"""

from __future__ import annotations

import random
import threading
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from typing import Any
from unittest import mock

from django.db import connection, transaction
from django.test import override_settings

from apps.accounts.models import Membership, Team, User
from apps.alerting.actions import Event, ingest
from apps.catalog import actions as catalog_actions
from apps.catalog.models import Service
from apps.core import invariants
from apps.core.errors import DomainError
from apps.escalations import engine
from apps.escalations.models import EscalationPolicy, EscalationRule, EscalationTarget
from apps.escalations.tasks import escalate_incident, sweep_due_escalations
from apps.incidents import actions as incident_actions
from apps.incidents.models import EventType, Incident, Status
from apps.notifications import actions as notification_actions
from apps.notifications.channels import (
    ChannelError,
    EmailChannel,
    InAppChannel,
    SmsChannel,
    VoiceChannel,
    WebhookChannel,
)
from apps.notifications.models import Notification, NotificationRule, UserContact
from apps.notifications.tasks import deliver_notification
from apps.schedules.models import (
    LayerMember,
    Rotation,
    Schedule,
    ScheduleLayer,
    ScheduleOverride,
)

FAULTS = (
    "broker_down",
    "message_lost",
    "message_dup",
    "crash",
    "concurrent_sweep",
    "clock_skew",
    "policy_edit",
    "mode_flip",
    "channel_failure",
)
START = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)  # a week before US DST starts


class SimulationFailure(AssertionError):
    pass


class InjectedCrash(RuntimeError):
    """Raised inside a transaction to simulate a worker dying mid-write."""


@dataclass
class Message:
    task: str
    args: tuple
    eta: datetime
    seq: int


@dataclass
class Report:
    seed: int
    operations: int = 0
    faults: Counter = field(default_factory=Counter)
    ops: Counter = field(default_factory=Counter)
    incidents_opened: int = 0
    incidents_resolved: int = 0
    notifications: int = 0
    sends: int = 0
    invariant_checks: int = 0
    log: list[str] = field(default_factory=list)

    def summary(self) -> str:
        faults = ", ".join(f"{k}={v}" for k, v in sorted(self.faults.items())) or "none"
        return (
            f"seed={self.seed}  operations={self.operations}  "
            f"incidents opened={self.incidents_opened} resolved={self.incidents_resolved}  "
            f"notifications={self.notifications} sends={self.sends}  "
            f"invariant checks={self.invariant_checks}\n  faults: {faults}"
        )


class Simulation:
    def __init__(self, seed: int, operations: int = 600, *, check_every: int = 1) -> None:
        self.seed = seed
        self.rng = random.Random(seed)  # noqa: S311 - seeded on purpose, not security
        self.target_ops = operations
        self.check_every = check_every
        self.report = Report(seed=seed)
        self.now = START
        self.queue: list[Message] = []
        self._msg_seq = 0
        self._deferred: list[tuple[str, str]] = []
        self.broker_down_until: datetime | None = None
        self.email_flaky = False
        self.sends: Counter[int] = Counter()
        self.first_response: dict[int, datetime] = {}
        self.snapshots: dict[int, dict] = {}
        self.services: list[Service] = []
        self.users_by_team: dict[int, list[User]] = {}
        self.policies: list[EscalationPolicy] = []
        self._clock: Any = None
        self._lock = threading.Lock()

    # --- public ----------------------------------------------------------------------------

    def run(self) -> Report:
        import time_machine  # dev dependency: the simulator is a test harness

        with time_machine.travel(self.now, tick=False) as clock, self._patched():
            self._clock = clock
            self._build_fixture()
            for _ in range(self.target_ops):
                self._step()
            self._drain()
        return self.report

    # --- infrastructure: clock, broker, channels -------------------------------------------

    def _set_now(self, at: datetime) -> None:
        self.now = at
        self._clock.move_to(at)

    def _advance(self, delta: timedelta) -> None:
        self._set_now(self.now + delta)

    @contextmanager
    def _patched(self) -> Iterator[None]:
        sim = self

        def apply_async(task_name: str) -> Callable[..., None]:
            def _apply(
                args: tuple = (), kwargs: dict | None = None, eta: datetime | None = None, **_: Any
            ) -> None:
                if sim.broker_down_until and sim.now < sim.broker_down_until:
                    sim.report.faults["broker_down"] += 1
                    raise ConnectionError("simulated broker outage")
                with sim._lock:
                    roll = sim.rng.random()
                    if roll < 0.05:
                        sim.report.faults["message_lost"] += 1
                        return
                    copies = 2 if roll > 0.93 else 1
                    if copies == 2:
                        sim.report.faults["message_dup"] += 1
                    for _copy in range(copies):
                        sim._msg_seq += 1
                        sim.queue.append(
                            Message(task_name, tuple(args), eta or sim.now, sim._msg_seq)
                        )

            return _apply

        def email_send(channel: EmailChannel, notification: Notification) -> None:
            if sim.email_flaky and sim.rng.random() < 0.5:
                sim.report.faults["channel_failure"] += 1
                raise ChannelError("simulated SMTP failure")
            sim._record_send(notification)

        def in_app_send(channel: InAppChannel, notification: Notification) -> None:
            sim._record_send(notification)

        def external_send(channel: Any, notification: Notification) -> None:
            # SMS, voice and webhook share one fake: flaky like SMTP, otherwise they just record.
            if sim.email_flaky and sim.rng.random() < 0.5:
                sim.report.faults["channel_failure"] += 1
                raise ChannelError("simulated carrier failure")
            sim._record_send(notification)

        with (
            override_settings(
                TWILIO_ACCOUNT_SID="sim",
                TWILIO_AUTH_TOKEN="sim",  # noqa: S106 - a fake for the simulator
                TWILIO_FROM_NUMBER="+15005550006",
            ),
            mock.patch.object(escalate_incident, "apply_async", apply_async("escalate")),
            mock.patch.object(deliver_notification, "apply_async", apply_async("deliver")),
            mock.patch.object(EmailChannel, "send", email_send),
            mock.patch.object(InAppChannel, "send", in_app_send),
            mock.patch.object(SmsChannel, "send", external_send),
            mock.patch.object(VoiceChannel, "send", external_send),
            mock.patch.object(WebhookChannel, "send", external_send),
        ):
            yield

    def _defer_failure(self, invariant: str, detail: str) -> None:
        """Record a violation seen inside a channel send.

        `deliver` rightly swallows any exception a channel raises (a poison message must not
        be retried forever), so raising here would be silently turned into a failed
        notification. The step loop raises it instead.
        """
        self._deferred.append((invariant, detail))

    def _record_send(self, notification: Notification) -> None:
        incident = Incident.objects.select_related("service").get(pk=notification.incident_id)
        self.sends[notification.pk] += 1
        self.report.sends += 1
        if self.sends[notification.pk] > 1:
            self._defer_failure(
                "I4",
                f"notification {notification.pk} ({notification.idempotency_key}) "
                f"sent {self.sends[notification.pk]} times",
            )
        if incident.service.mode == Service.Mode.DEBUG:
            self._defer_failure(
                "I12",
                f"notification {notification.pk} sent for debug service {incident.service.name}",
            )
        if notification.not_before is not None:
            if self.now < notification.not_before:
                self._defer_failure(
                    "I19",
                    f"notification {notification.pk} sent at {self.now}, "
                    f"before its time {notification.not_before}",
                )
            if incident.status != Status.TRIGGERED:
                self._defer_failure(
                    "I18",
                    f"delayed step {notification.pk} sent while incident "
                    f"#{incident.number} was {incident.status}",
                )
        if incident.status == Status.RESOLVED:
            self._defer_failure(
                "C1",
                f"notification {notification.pk} sent for incident "
                f"#{incident.number}, resolved at {incident.resolved_at}",
            )

    # --- fixture ------------------------------------------------------------------------------

    def _build_fixture(self) -> None:
        rng = self.rng
        zones = ["America/New_York", "Europe/London", "Australia/Lord_Howe", "UTC"]
        for t in range(rng.randint(2, 3)):
            team = Team.objects.create(name=f"Team {t}", slug=f"sim-team-{self.seed}-{t}")
            users = [
                User.objects.create_user(
                    f"sim{self.seed}-{t}-{u}@sim.invalid", None, name=f"U{t}.{u}"
                )
                for u in range(rng.randint(3, 6))
            ]
            for user in users:
                Membership.objects.create(team=team, user=user, role=Membership.Role.RESPONDER)
                self._random_plan(user)
            self.users_by_team[team.pk] = users
            schedules = [
                self._random_schedule(team, users, rng.choice(zones), s)
                for s in range(rng.randint(1, 2))
            ]
            for p in range(rng.randint(1, 2)):
                policy = EscalationPolicy.objects.create(
                    team=team, name=f"P{t}.{p}", num_loops=rng.randint(0, 3)
                )
                self._write_rules(policy, users, schedules)
                self.policies.append(policy)
            for s in range(rng.randint(2, 3)):
                self.services.append(
                    Service.objects.create(
                        team=team,
                        name=f"svc-{t}-{s}",
                        escalation_policy=rng.choice(
                            [p for p in self.policies if p.team_id == team.pk]
                        ),
                    )
                )

    def _random_plan(self, user: User) -> None:
        """Half the people keep the default; the rest get a verified phone and a plan."""
        rng = self.rng
        if rng.random() < 0.5:
            return
        UserContact.objects.create(
            user=user,
            phone_number=f"+1415555{user.pk % 10000:04d}",
            phone_verified_at=START,
            webhook_url="https://hooks.sim.invalid/services/x",
            webhook_secret="sim-secret",  # noqa: S106
        )
        plan = [("sms", 0), ("voice", rng.choice([2, 5])), ("sms", rng.choice([1, 3])),
                ("email", rng.choice([0, 2])), ("webhook", rng.choice([0, 1]))]  # fmt: skip
        for position, (channel, delay) in enumerate(rng.sample(plan, k=rng.randint(1, len(plan)))):
            NotificationRule.objects.create(
                user=user,
                position=position,
                channel=channel,
                delay_minutes=delay,
                urgency=rng.choice(["any", "any", "any", "high", "low"]),
            )

    def _random_schedule(self, team: Team, users: list[User], zone: str, n: int) -> Schedule:
        rng = self.rng
        schedule = Schedule.objects.create(team=team, name=f"S{team.pk}.{n}", timezone=zone)
        for priority in range(rng.randint(1, 3)):
            rotation = rng.choice([Rotation.DAILY, Rotation.WEEKLY, Rotation.CUSTOM])
            layer = ScheduleLayer.objects.create(
                schedule=schedule,
                name=f"L{priority}",
                priority=priority,
                rotation_type=rotation,
                turn_count=rng.randint(1, 3),
                turn_length=timedelta(hours=rng.randint(1, 24))
                if rotation == Rotation.CUSTOM
                else None,
                start=START - timedelta(days=rng.randint(0, 30), minutes=rng.randint(0, 1439)),
                handoff_time=time(rng.randint(0, 23), rng.choice([0, 30])),
            )
            # Occasionally an empty layer: escalations must skip it (I7 no-responder path).
            members = rng.sample(users, k=rng.randint(0 if rng.random() < 0.15 else 1, len(users)))
            for position, user in enumerate(members):
                LayerMember.objects.create(layer=layer, user=user, position=position)
        for _ in range(rng.randint(0, 3)):  # overlapping overrides
            start = START + timedelta(hours=rng.randint(-12, 72))
            ScheduleOverride.objects.create(
                schedule=schedule,
                user=rng.choice(users),
                start=start,
                end=start + timedelta(hours=rng.randint(1, 30)),
            )
        return schedule

    def _write_rules(
        self, policy: EscalationPolicy, users: list[User], schedules: list[Schedule]
    ) -> None:
        rng = self.rng
        policy.rules.all().delete()
        for level in range(rng.randint(1, 4)):
            rule = EscalationRule.objects.create(
                policy=policy, level=level, delay_minutes=rng.randint(1, 15)
            )
            for position in range(rng.randint(1, 2)):
                if rng.random() < 0.5:
                    EscalationTarget.objects.create(
                        rule=rule, position=position, target_schedule=rng.choice(schedules)
                    )
                else:
                    EscalationTarget.objects.create(
                        rule=rule, position=position, target_user=rng.choice(users)
                    )

    # --- the operation loop ----------------------------------------------------------------------

    OPS: tuple[tuple[str, int], ...] = (
        ("trigger", 18),
        ("source_event", 4),
        ("human_action", 16),
        ("resolve_backlog", 4),
        ("advance_clock", 14),
        ("run_worker", 14),
        ("sweep", 8),
        ("concurrent_sweep", 2),
        ("skewed_sweep", 2),
        ("notification_sweep", 3),
        ("expire_modes", 2),
        ("mode_flip", 2),
        ("policy_edit", 2),
        ("crash", 3),
        ("broker_outage", 1),
        ("flaky_email", 1),
    )

    def _step(self) -> None:
        names = [name for name, _ in self.OPS]
        weights = [weight for _, weight in self.OPS]
        op = self.rng.choices(names, weights)[0]
        before_events = invariants.non_delivery_event_count()
        touched: set[int] = set()
        expected = getattr(self, f"_op_{op}")(touched)
        self.report.operations += 1
        self.report.ops[op] += 1
        self.report.log.append(
            f"{self.report.operations:5d} {self.now:%m-%d %H:%M:%S} {op} "
            f"touched={sorted(touched)[:6]} expected_events={expected}"
        )
        delta = invariants.non_delivery_event_count() - before_events
        if expected is not None and delta != expected:
            self._fail("I10", f"{op} wrote {delta} timeline events, expected {expected}")
        if self.report.operations % self.check_every == 0:
            self._check(touched)

    def _check(self, touched: set[int] | None = None) -> None:
        if self._deferred:
            self._fail(*self._deferred[0])
        self.report.invariant_checks += 1
        violations = invariants.check_invariants(touched)
        if violations:
            self._fail(violations[0].invariant, "; ".join(str(v) for v in violations[:3]))
        for incident in Incident.objects.filter(pk__in=list(touched or [])):
            frozen = self.snapshots.setdefault(incident.pk, incident.escalation_snapshot)
            if incident.escalation_snapshot != frozen:
                self._fail("I17", f"incident {incident.pk} snapshot changed")
            if incident.first_response_at is not None:
                first = self.first_response.setdefault(incident.pk, incident.first_response_at)
                if first != incident.first_response_at:
                    self._fail(
                        "I9",
                        f"incident {incident.pk} first_response_at changed "
                        f"{first} → {incident.first_response_at}",
                    )

    def _fail(self, invariant: str, detail: str) -> None:
        tail = "\n".join(self.report.log[-25:])
        raise SimulationFailure(
            f"\n\nInvariant {invariant} broken — reproduce with: "
            f"python manage.py simulate --seed {self.seed} --operations {self.target_ops}\n"
            f"{detail}\n\nLast operations:\n{tail}\n\n{self.report.summary()}"
        )

    # --- workload operations: each returns the number of timeline events it should write ---

    def _open_incidents(self) -> list[Incident]:
        return list(Incident.objects.exclude(status=Status.RESOLVED).order_by("pk"))

    def _op_trigger(self, touched: set[int]) -> int | None:
        service = self.rng.choice(self.services)
        service.refresh_from_db()
        key = f"k{self.rng.randint(0, 6)}"  # a small pool: lots of collisions
        severity = self.rng.choice(["critical", "critical", "error", "warning", "info"])
        before = set(Incident.objects.values_list("pk", flat=True))
        result = ingest(
            service,
            Event(
                action="trigger",
                dedup_key=key,
                summary=f"{key} fired",
                severity=severity,
                source="sim",
            ),
        )
        touched.add(result.incident_id or 0)
        if not result.created:
            return 1  # alert_attached
        self.report.incidents_opened += 1
        incident = Incident.objects.get(pk=result.incident_id or 0)
        if incident.pk in before:
            self._fail("I1", f"new incident {incident.pk} already existed")
        no_responder = incident.events.filter(type=EventType.NO_RESPONDER).exists()
        return 1 + int(no_responder)

    def _op_source_event(self, touched: set[int]) -> int | None:
        service = self.rng.choice(self.services)
        key = f"k{self.rng.randint(0, 6)}"
        action = self.rng.choice(["acknowledge", "resolve"])
        result = ingest(service, Event(action=action, dedup_key=key, source="sim-monitor"))
        if result.incident_id:
            touched.add(result.incident_id)
        if action == "resolve" and result.status == "accepted":
            self.report.incidents_resolved += 1
        return 1 if result.status == "accepted" else 0

    def _human_action(self, incident: Incident) -> tuple[str, Callable[[], Any]]:
        team_users = self.users_by_team[incident.service.team_id]
        actor = self.rng.choice(team_users)
        choice = self.rng.choice(
            ["acknowledge", "unacknowledge", "resolve", "reassign", "escalate", "note"]
        )
        calls: dict[str, Callable[[], Any]] = {
            "acknowledge": lambda: incident_actions.acknowledge(incident.pk, actor=actor),
            "unacknowledge": lambda: incident_actions.unacknowledge(incident.pk, actor=actor),
            "resolve": lambda: incident_actions.resolve(incident.pk, actor=actor),
            "reassign": lambda: incident_actions.reassign(
                incident.pk, actor=actor, assignee=self.rng.choice(team_users)
            ),
            "escalate": lambda: incident_actions.escalate(incident.pk, actor=actor),
            "note": lambda: incident_actions.add_note(incident.pk, actor=actor, text="sim note"),
        }
        return choice, calls[choice]

    def _op_resolve_backlog(self, touched: set[int]) -> int | None:
        """Resolve an incident whose pages are still queued (C1: they must not go out later)."""
        backlog = list(
            Incident.objects.filter(
                status__in=(Status.TRIGGERED, Status.ACKNOWLEDGED),
                notifications__status=Notification.Status.PENDING,
            ).distinct()
        )
        if not backlog:
            return 0
        incident = self.rng.choice(backlog)
        touched.add(incident.pk)
        incident_actions.resolve(
            incident.pk, actor=self.rng.choice(self.users_by_team[incident.service.team_id])
        )
        self.report.incidents_resolved += 1
        return 1

    def _op_human_action(self, touched: set[int]) -> int | None:
        open_ = self._open_incidents()
        if not open_:
            return 0
        incident = self.rng.choice(open_)
        touched.add(incident.pk)
        name, call = self._human_action(incident)
        try:
            call()
        except DomainError:
            return 0  # invalid transition / nothing left to escalate: no event
        if name == "resolve":
            self.report.incidents_resolved += 1
        return 1

    def _op_crash(self, touched: set[int]) -> int | None:
        """A worker dies after writing pages but before commit: nothing may persist."""
        open_ = self._open_incidents()
        if not open_:
            return 0
        incident = self.rng.choice(open_)
        touched.add(incident.pk)
        before = self._incident_state(incident.pk)
        real_page = notification_actions.page

        def page_then_die(*args: Any, **kwargs: Any) -> Any:
            real_page(*args, **kwargs)
            raise InjectedCrash("worker died mid-transaction")

        name, call = self._human_action(incident)
        with (
            mock.patch("apps.incidents.actions.page", page_then_die),
            mock.patch("apps.escalations.engine.page", page_then_die),
        ):
            try:
                call()
            except InjectedCrash:
                pass
            except DomainError:
                return 0
            else:
                # Actions that don't page (acknowledge, resolve, note) commit normally.
                if name == "resolve":
                    self.report.incidents_resolved += 1
                return 1
        self.report.faults["crash"] += 1
        after = self._incident_state(incident.pk)
        if before != after:
            self._fail("crash", f"rollback left partial state after {name}: {before} → {after}")
        return 0

    def _incident_state(self, incident_id: int) -> tuple:
        incident = Incident.objects.get(pk=incident_id)
        return (
            incident.status,
            incident.escalation_level,
            incident.escalation_loop,
            incident.next_escalation_at,
            incident.assignee_id,
            incident.first_response_at,
            incident.events.count(),
            incident.notifications.count(),
        )

    def _op_advance_clock(self, touched: set[int]) -> int | None:
        self._advance(timedelta(seconds=self.rng.choice([5, 30, 60, 120, 300, 600, 1800])))
        return 0

    def _op_run_worker(self, touched: set[int]) -> int | None:
        """Execute every due message, in a random order (workers don't preserve order)."""
        due = [m for m in self.queue if m.eta <= self.now]
        self.queue = [m for m in self.queue if m.eta > self.now]
        self.rng.shuffle(due)
        moved = 0
        for message in due:
            if message.task == "escalate":
                touched.add(message.args[0])
                moved += int(escalate_incident.run(*message.args))
            else:
                notification = Notification.objects.filter(pk=message.args[0]).first()
                if notification:
                    touched.add(notification.incident_id)
                try:
                    deliver_notification.run(*message.args)
                except ChannelError:
                    # Celery's autoretry: back off and try again.
                    attempts = Notification.objects.get(pk=message.args[0]).attempts
                    self._msg_seq += 1
                    self.queue.append(
                        Message(
                            "deliver",
                            message.args,
                            self.now + timedelta(seconds=5 * 2**attempts),
                            self._msg_seq,
                        )
                    )
        return moved

    def _sweep(self, touched: set[int], now: datetime) -> int:
        due = {pk: (level, loop) for pk, level, loop in engine.due_incidents(now)}
        touched.update(due)
        moved = sweep_due_escalations.run()
        # I7: everything that was due has advanced or cleared its timer.
        for incident in Incident.objects.filter(pk__in=list(due)):
            if incident.status != Status.TRIGGERED:
                continue
            advanced = (incident.escalation_level, incident.escalation_loop) != due[incident.pk]
            if not advanced and incident.next_escalation_at is not None:
                self._fail(
                    "I7",
                    f"incident {incident.pk} was due at {now} but neither advanced "
                    f"nor cleared (timer {incident.next_escalation_at})",
                )
        return moved

    def _op_sweep(self, touched: set[int]) -> int | None:
        return self._sweep(touched, self.now)

    def _op_skewed_sweep(self, touched: set[int]) -> int | None:
        skew = timedelta(seconds=self.rng.randint(-90, 90))
        self.report.faults["clock_skew"] += 1
        real = self.now
        self._set_now(real + skew)
        try:
            return self._sweep(touched, real + skew)
        finally:
            self._set_now(real)

    def _op_concurrent_sweep(self, touched: set[int]) -> int | None:
        """Two sweepers in real threads, racing over the same due set."""
        if connection.in_atomic_block:
            return self._op_sweep(touched)  # threads can't see uncommitted test data
        self.report.faults["concurrent_sweep"] += 1
        touched.update(pk for pk, _, _ in engine.due_incidents(self.now))
        results: list[int] = []
        errors: list[BaseException] = []
        barrier = threading.Barrier(2)

        def sweeper() -> None:
            try:
                barrier.wait()
                results.append(sweep_due_escalations.run())
            except BaseException as exc:
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=sweeper) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        if errors:
            raise errors[0]
        return sum(results)

    def _op_notification_sweep(self, touched: set[int]) -> int | None:
        notification_actions.redispatch_stuck()
        return 0

    def _op_expire_modes(self, touched: set[int]) -> int | None:
        open_maintenance = (
            Incident.objects.filter(is_maintenance=True, service__mode_until__lte=self.now)
            .exclude(status=Status.RESOLVED)
            .exclude(service__mode=Service.Mode.ACTIVE)
        )
        expected = open_maintenance.count()
        touched.update(open_maintenance.values_list("pk", flat=True))
        catalog_actions.expire_service_modes()
        self.report.incidents_resolved += expected
        return expected

    def _op_mode_flip(self, touched: set[int]) -> int | None:
        service = self.rng.choice(self.services)
        service.refresh_from_db()
        mode = self.rng.choice([Service.Mode.ACTIVE, Service.Mode.DEBUG, Service.Mode.MAINTENANCE])
        leaving = service.mode == Service.Mode.MAINTENANCE and mode != Service.Mode.MAINTENANCE
        open_maintenance = Incident.objects.filter(service=service, is_maintenance=True).exclude(
            status=Status.RESOLVED
        )
        expected = open_maintenance.count() if leaving else 0
        touched.update(open_maintenance.values_list("pk", flat=True))
        self.report.faults["mode_flip"] += 1
        until = (
            None
            if mode == Service.Mode.ACTIVE
            else self.now + timedelta(minutes=self.rng.randint(5, 240))
        )
        catalog_actions.set_mode(service, mode, until=until)
        self.report.incidents_resolved += expected
        return expected

    def _op_policy_edit(self, touched: set[int]) -> int | None:
        policy = self.rng.choice(self.policies)
        users = self.users_by_team[policy.team_id]
        schedules = list(Schedule.objects.filter(team_id=policy.team_id))
        self.report.faults["policy_edit"] += 1
        with transaction.atomic():
            self._write_rules(policy, users, schedules)
            policy.num_loops = self.rng.randint(0, 3)
            policy.save()
        touched.update(
            Incident.objects.filter(service__escalation_policy=policy)
            .exclude(status=Status.RESOLVED)
            .values_list("pk", flat=True)
        )
        return 0

    def _op_broker_outage(self, touched: set[int]) -> int | None:
        self.broker_down_until = self.now + timedelta(minutes=self.rng.randint(1, 20))
        return 0

    def _op_flaky_email(self, touched: set[int]) -> int | None:
        self.email_flaky = not self.email_flaky
        return 0

    # --- drain -------------------------------------------------------------------------------

    def _drain(self) -> None:
        """Faults off; run time forward until nothing is due, queued or pending (I5, I6)."""
        self.broker_down_until = None
        self.email_flaky = False
        self._check(set(Incident.objects.values_list("pk", flat=True)))
        longest = max(
            (
                len(i.escalation_snapshot.get("rules") or [])
                * (i.escalation_snapshot.get("num_loops", 0) + 1)
                for i in Incident.objects.all()
            ),
            default=0,
        )
        for _ in range(longest * 3 + 20):
            touched: set[int] = set()
            self._advance(timedelta(minutes=16))  # past every delay (max 15) and STUCK_AFTER
            self._op_run_worker(touched)
            self._sweep(touched, self.now)
            notification_actions.redispatch_stuck()
            self._op_run_worker(touched)
            live = Incident.objects.filter(
                status=Status.TRIGGERED, next_escalation_at__isnull=False
            ).exists()
            if not live and not self.queue and invariants.pending_notifications() == 0:
                break
        else:
            stuck = list(
                Incident.objects.filter(
                    status=Status.TRIGGERED, next_escalation_at__isnull=False
                ).values_list("pk", "escalation_level", "escalation_loop")[:5]
            )
            self._fail(
                "I6/I5",
                f"system did not drain: live timers {stuck}, queued "
                f"{len(self.queue)}, pending {invariants.pending_notifications()}",
            )
        self._check(set(Incident.objects.values_list("pk", flat=True)))
        self.report.notifications = Notification.objects.count()
