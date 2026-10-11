# Decision log

Each entry: what was decided, what else was on the table, and why. Newest decisions that
deviate from the original brief are marked **(deviation)**.

---

## 1. Seven deep capabilities instead of ten shallow ones

**Decision.** Build services, ingest, incidents, escalation, scheduling, notifications and
analytics, each end to end and tested. Leave out runbooks, status pages, SMS/phone, and
personal notification rules.

**Alternatives.** A wider feature list with thinner implementations (e.g. status pages with
no real incident model behind them).

**Why.** The interesting engineering in incident response is in the core loop: an alert
becomes exactly one incident, the right person is paged exactly once, and the timeline is
trustworthy. A shallow version of ten features demonstrates CRUD; a deep version of seven
demonstrates distributed-systems judgment. The non-goals are listed in the README so the
omission reads as a choice.

## 2. Escalation timing lives in Postgres, not in Celery countdowns

**Decision.** `Incident.next_escalation_at` is the timer. An ETA task is enqueued on commit
for low latency, and a Beat sweeper (`sweep_due_escalations`, every 30 s) escalates anything
whose timer has passed.

**Alternatives.** Celery `countdown`/`eta` alone; a dedicated scheduler (APScheduler, a
timer wheel); Redis sorted sets keyed by due time.

**Why.** A countdown exists only as a broker message. Redis is configured without
persistence (it's a disposable broker), so a restart drops every pending escalation, and
with them the page that should have woken someone up. Keeping the due time in the database
makes the broker an optimisation: if the ETA message is lost, the sweeper catches the
incident at most ~30 s late. `make chaos-redis` proves it live (wipe Redis + kill the worker
mid-incident; it still escalates), and `test_sweeper_recovers_when_the_eta_message_is_lost`
proves it in CI.

## 3. A guarded update plus idempotency keys prevents double paging

**Decision.** `engine.escalate(id, level, loop, now)` locks the row with
`SELECT … FOR UPDATE SKIP LOCKED` and only proceeds if the incident is *still* triggered, at
*that* level and loop, and already due. Every page is a `Notification` row with a unique
`idempotency_key` (`incident:{id}:level:{n}:loop:{k}:user:{id}:channel:{c}`).

**Alternatives.** A distributed lock in Redis; "check then act" in application code;
de-duplicating on the delivery side only.

**Why.** Two callers (ETA task and sweeper) are *designed* to race. The guard makes the
loser a no-op instead of a second escalation, and the unique key makes a retried delivery
task find the existing row instead of paging again. Both guarantees are enforced by Postgres,
so they hold across processes, machines and restarts. Covered by
`test_eta_task_and_sweeper_double_fire_pages_once` and a 4-thread concurrency test.

## 4. Dedup is a partial unique index, not "find, else create"

**Decision.** `UNIQUE (service_id, dedup_key) WHERE status <> 'resolved'`. Ingest tries to
attach to an open incident; if none exists it inserts. A concurrent insert that loses the
race gets `IntegrityError`, and the retry attaches to the winner.

**Alternatives.** Application-level "get or create"; a Redis lock per dedup key; serialisable
transactions.

**Why.** "Find, else create" is a textbook race: two identical alerts arriving together both
find nothing and both create. The partial index makes the second insert impossible while
still letting a *resolved* incident's key be reused for a new incident. The 8-thread test
(`test_concurrent_triggers_with_one_key_create_exactly_one_incident`) fires the same alert
concurrently and asserts one incident with eight attached alerts.

## 5. All side effects dispatch via `transaction.on_commit`

**Decision.** Celery tasks are enqueued only after the transaction that justified them
commits (`apps/core/dispatch.py`), and an enqueue failure is logged rather than raised.

**Alternatives.** Enqueue inline; a transactional outbox table.

**Why.** Enqueue-before-commit lets a fast worker read a row that doesn't exist yet, or act
on a change that is about to roll back. Swallowing broker errors on dispatch keeps a Redis
outage from failing the API request; the database already holds the durable intent
(`next_escalation_at`, pending `Notification` rows), and the sweepers re-drive it. That's a
lightweight outbox: the "outbox" is the domain rows themselves.

## 6. Daily and weekly rotations count local calendar days

**Decision.** Rotation turns are computed from the *local date* of the shift in the
schedule's IANA zone (`_shift_day`), with handoff at a local wall-clock time. Custom
rotations use absolute hours.

**Alternatives.** Count 24-hour periods since the layer start (simple, and wrong twice a
year).

**Why.** People agree to "handoff at 09:00", not "every 86 400 seconds". Counting days keeps
09:00 at 09:00 through DST: the DST-day shift is simply 23 or 25 hours long. The resolver is
pure (no DB), so New York and London spring-forward/fall-back cases, plus a handoff inside the
non-existent 02:30 hour, are tested exhaustively. Custom rotations ("every 12 h") stay
absolute by design: that's what follow-the-sun teams mean.

## 7. Nobody on call → skip to the next level on the next sweep

**Decision.** If a level resolves to nobody (empty rotation, deactivated user), log
`no_responder` and make the incident due immediately rather than waiting out the delay.

**Alternatives.** Wait the full delay anyway; fail loudly and stop.

**Why.** Waiting means a critical incident silently pages no one for five minutes. Stopping
means it pages no one ever. Moving on is what a human dispatcher would do, and the timeline
records why. Low-urgency incidents never auto-escalate, so they don't skip either.

## 8. Polling over WebSockets

**Decision.** TanStack Query polls incident lists and details every 10 s (bell: 15 s).

**Alternatives.** Django Channels / WebSockets; server-sent events.

**Why.** It adds no new infrastructure (an ASGI server, a channel layer, sticky connections)
for a dashboard where 10 s staleness is fine. The real paging path (email) doesn't depend on
the browser at all. Optimistic updates make the user's own actions feel instant. If this
needed sub-second fan-out, SSE from a small endpoint would be the next step.

## 9. The escalation policy is snapshotted when an incident opens

**Decision.** `Incident.escalation_snapshot` stores the policy's levels, delays, loop count
and target identities as versioned JSON. Schedule targets still resolve to whoever is on call
when each level fires.

**Alternatives.** Always read the live policy; version policies as immutable rows.

**Why.** An admin editing a policy at 3 a.m. must not rewire an incident already in flight,
or silently delete the level that was about to page. Snapshotting the *structure* but not the
*people* keeps both promises: the path is frozen, but a 09:00 handoff still routes to the new
on-call. The idea of freezing the policy at open time is borrowed from how Grafana OnCall
behaves. No code was taken from it (it's AGPL); the implementation is original.

## 10. Debug and maintenance modes on services

**Decision.** `maintenance` folds every alert into one quiet low-urgency incident that never
pages and resolves when the window ends. `debug` runs the whole pipeline (incident,
escalation, timeline) but stores notifications as `dry_run`.

**Alternatives.** Simply disable the integration key during maintenance; a global "test
mode".

**Why.** Disabling the key loses the alerts; folding keeps a record without waking anyone.
Debug mode answers "would this have paged the right people?" without paging them, which is
how you safely tune a new integration. Both modes expire automatically
(`expire_service_modes`, every 60 s) because people forget to turn them off.

## 11. Time to first response is the headline metric

**Decision.** The dashboard leads with time to first response (trigger → first human
acknowledge, unacknowledge, resolve, reassign or manual escalate), alongside MTTA and MTTR.

**Alternatives.** Lead with MTTA, the industry default.

**Why.** MTTA misses the responder who reassigns to the right owner in 30 seconds, or
escalates immediately because they're in a meeting. Both are fast, correct responses that
MTTA scores as slow. Source-driven acknowledgements (the monitor auto-resolving) never count:
they measure the alert, not the team. Notes don't count either; typing isn't responding.

## 12. System limits live in one module

**Decision.** `apps/core/limits.py` defines every limit (512 KB payload, 10 levels, 5 targets
per level, 5 layers, 50 members, 5 000-char notes). Serializers and the Events API enforce
them via `limits.enforce`, which returns HTTP 422 `limit_exceeded`. The frontend mirrors the
values to show limits inline.

**Alternatives.** Scatter `max_length` and ad-hoc checks across serializers.

**Why.** One place to read, change and document. A distinct error code lets clients tell
"you broke a rule" (`validation_error`) from "you hit a ceiling" (`limit_exceeded`).

---

## Deviations from the original brief

### 13. Escalation targets get their own table **(deviation)**

The brief's `EscalationRule` had both "CHECK exactly one target" and "≤ 5 targets per level".
A row can't hold one target and five. The model is now `EscalationRule` (one per level:
level, delay) plus `EscalationTarget` (one per target, with the exactly-one-of-user-or-schedule
CHECK). That's 15 tables instead of 14, and both constraints hold in Postgres.

### 14. A `viewer` membership role **(deviation)**

The brief lists a Viewer persona but only `admin`/`responder` roles. `Membership.role` adds
`viewer`: team members who can read everything but act on nothing. Permissions are ranked
viewer < responder < admin in `core/permissions.py`.

### 15. Notification rows are written in the escalating transaction **(deviation)**

The brief's engine sketch dispatches `notify_responders.delay(...)` on commit, which would
create the rows later in a task. If Redis loses that message, nobody is paged and nothing
records that someone should have been. Pulse instead creates the `Notification` rows inside
the same transaction as the escalation, and only delivery happens in a task. The sweeper
`sweep_stuck_notifications` re-dispatches rows still pending after two minutes.

### 16. Versions newer or older than the brief's floor, where needed

See [`STACK.md`](STACK.md). In short: Django 6.0 (6.1 is out, but not every dependency
declares support yet); TypeScript 5.9 (7.x breaks typescript-eslint and openapi-typescript
peer ranges); React Router 7 (v8 exists; v7 meets the floor with a stable API).

### 17. Sequence-backed incident numbers

`Incident.number` uses a Postgres sequence (`db_default=nextval(...)`), so numbers are
human-friendly and race-free without a counter row lock. Like any sequence it can skip
numbers after a rollback; that's acceptable for an identifier.

---

## What the property tests found

Phase 2 of the hardening work (see [`INVARIANTS.md`](INVARIANTS.md)) replaced hand-picked
on-call cases with generated ones. Each defect below has a focused regression test that
fails against the old code (verified by restoring the old file and re-running it).

### F1. The pager went back to yesterday's responder during a fall-back hour

**Found by** `test_daily_and_weekly_handoffs_land_on_the_local_handoff_time_across_dst`,
falsifying example: New York, daily rotation, handoff 01:30, 2025-11-02.

**Cause.** `_shift_day` compared wall-clock times. After a fall-back, 01:00–02:00 happens
twice; the second 01:15 reads earlier than a 01:30 handoff even though it is 45 minutes
after it, so the resolver assigned the previous shift day for the repeated half hour.
`render_shifts` placed the boundary correctly, so the timeline and the escalation engine
disagreed for 30 minutes a year, and the engine would have paged the wrong person.

**Fix.** The shift day is now *the latest day whose handoff instant is at or before `at`*,
comparing instants only. The DST-gap search no longer depends on `_shift_day`.

**Why the example tests missed it.** They covered fall-back with a 09:00 handoff, which is
nowhere near the repeated hour. The property generator weights handoffs towards
01:00–03:00 and probes every 5 minutes around each transition.

### F2. Zero-length custom turns could reach the resolver

**Found by** the adversarial review of I2. Only the API's `turn_length_hours >= 1` rejected
them; the database constraint checked only `NOT NULL`, so the admin could save a zero or
negative turn and every `on_call` for that schedule would raise. A `CHECK
(turn_length > 0)` constraint (`layer_turn_length_positive`) now refuses it.
