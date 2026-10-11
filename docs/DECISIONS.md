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

## 18. HSTS is opt-in, and set to one year in the deploy config

**Decision.** `SECURE_HSTS_SECONDS` defaults to `0` in `config.settings.prod`. The Render
blueprint sets it to `31536000` (one year), without `includeSubdomains` or `preload`.

**Alternatives.** Default to a year in code; leave it off everywhere.

**Why.** HSTS is sticky: once a browser has seen the header for a host it refuses plain HTTP
there for the whole period, and the only fix is waiting it out. The same prod settings run
the documented `docker-compose.prod.yml` stack on `http://localhost:8080`, where a year-long
default would lock a developer's browser out of `localhost` for a year. So the code stays
safe-by-default for that case and the deploy that is HTTPS-only turns it on explicitly. It is
deliberately not preloaded: preload is effectively irreversible and shouldn't be decided by a
demo blueprint.

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

---

## What the simulator found

`manage.py simulate --seed N` (see [`INVARIANTS.md`](INVARIANTS.md)) drives the real code against
a real Postgres with a virtual clock and injected faults: broker down, messages lost and
duplicated, a worker dying after writing pages but before commit, concurrent sweepers, clock
skew, policies edited mid-flight, service modes flipped mid-flight, and a flaky email channel.
`apps/core/invariants.py` runs after every operation. Each defect below has a focused
regression test that fails against the old code.

### S1. Human actions paged people from a maintenance incident (I13)

**Found by** seed 20261011, first run. **Cause.** I13 was enforced where an incident opens
(`open_incident` returns before paging), but `unacknowledge` and `reassign` call `page()`
directly, and manual `escalate` walks the policy. Acknowledge then unacknowledge on a
maintenance incident paged the on-call. **Fix.** `page()` refuses maintenance incidents, and
manual escalate on one is a `Conflict`. **Regression.**
`test_human_actions_on_a_maintenance_incident_never_page` fails 3 of 3 cases without it.

### S2. A delayed page woke someone for an incident that was already resolved (C1)

**Cause.** `deliver` checked the row's status and the service mode but not the incident. A
notification queued before resolution (broker outage, retry backoff, a lost message re-driven
by the sweeper) was sent afterwards. **Fix.** `deliver` marks it `cancelled` when the incident
is resolved (new status, migration `0002`). **Regression.**
`test_a_page_queued_before_resolution_is_never_sent_after_it` fails without the guard
(`sent` instead of `cancelled`).

### Two things about the simulator itself

- **It could not see S2 at first.** `deliver` deliberately catches every exception a channel
  raises (a poison message must not be retried forever), so a violation raised from inside
  the simulated `send` was swallowed as a failed notification. With the fix removed, 26 seeds
  passed. Violations seen inside `send` are now recorded and raised by the step loop; with
  the S2 fix removed, seeds 1 and 2 now fail within seconds. A checker that cannot fail was
  worth nothing, so this is the check that was verified, not assumed.
- **A checker gap, not a product bug.** Seed 1 reported I9 (`first_response_at` set with no
  human event) for an incident whose human resolve is recorded as `maintenance_ended`
  rather than `resolved`. The checker now counts that event.

---

## What the runtime checks found

Running the stack for real (`docker compose`, `make doctor`, see [`RUNBOOK.md`](RUNBOOK.md)) found faults that
no unit test could. Each has a guard that fails against the old behaviour (noted in brackets).

### R1. No email ever reached the inbox in dev
`.env.example` pinned `EMAIL_BACKEND` to the console backend, and an explicit backend beats `EMAIL_HOST`, so
the Mailpit wiring was silently bypassed. Found by sending an alert and finding an empty inbox. Fix: the
variable is gone from `.env.example` and compose forces SMTP to Mailpit. [`doctor`: the page must reach Mailpit]

### R2. `worker`, `beat` and the frontend had no healthcheck
`--wait` reported them "Healthy" while meaning only "the process exists". Now: workers answer a broker round
trip, beat checks that exactly one beat process runs, the frontend answers HTTP. [`compose ps`]

### R3. A page could wait about seven minutes after a Redis outage
A lost delivery message was re-driven by a sweep that ran every 5 minutes over rows older than 2. Now 60 s and
90 s: about 2.5 minutes. [`test_a_lost_deliver_message_is_redriven_within_three_minutes`]

### R4. `/readyz` pulled instances out of rotation exactly when Redis was down
Redis-down returned 503, though the API still ingests and commits without it. Now `degraded` with a 200;
only Postgres is required. [`test_redis_down_is_degraded_not_unready`, doctor drill]

### R5. A multi-line alert summary permanently failed the email page
The incident title is the raw summary and a header may not contain a newline, so the email failed five times and
gave up while the in-app page still arrived. Titles and subjects are collapsed to one line.
[`test_a_multi_line_summary_still_reaches_the_inbox_by_email`]

### R6. SMTP could not be configured, and `send_mail` ran under a row lock
Only the backend class was configurable, with no timeout, and the send happened inside a transaction holding
the notification row. Now host, port, TLS, credentials and a 10 s timeout come from the environment, and
`deliver` claims, sends with no transaction open, then settles, keeping send-once. [`test_delivery_claim.py`]

### R7. Login throttling trusted a client-supplied `X-Forwarded-For`
Rotating a forged prefix gave every attempt a fresh bucket (14 wrong passwords, then a successful login, in
the security audit). nginx now appends the peer, Django reads the address that many proxies from the right
(`NUM_PROXIES`), and the prod compose sets 1. [doctor: 13 forged attempts must reach 429; with `NUM_PROXIES`
unset the same check fails (verified)]

### R8. "The escalations queue is first" was false
`-Q escalations,notifications,default` is not a priority: kombu's Redis transport round-robins its queues. Paging
is now isolated by a worker that consumes only `escalations`. On a single-worker host all three queues still
share one process, which the docs now say.

### R9. A flaw in the drill, not the stack
The first API-crash drill used `docker compose kill`, which Docker treats as a manual stop, so the restart
policy correctly left the container down. The drill now simulates real crashes: SIGKILL every gunicorn worker
(the master must respawn them) and make PID 1 exit on its own (the restart policy must bring it back).

### R10. `make test` took nearly nine minutes in the container
`.env` exports `DJANGO_SETTINGS_MODULE=config.settings.dev`, and an environment variable beats the setting in
`pytest.ini`, so the suite ran on dev settings (real password hashing, the real broker) instead of test
settings: 8m42s for 240 tests, against under two minutes in CI. Found on the clean-clone run; the security
audit had flagged the same variable. pytest now pins the module with `--ds`.
[`test_the_suite_runs_on_test_settings_whatever_the_environment_says`]

### Smaller
`backend/.dockerignore` now excludes `.env*`, `*.rdb` and `.git`; the SPA is served with `nosniff`,
`X-Frame-Options` and `Referrer-Policy`; the throttle's fail-open path logs one line instead of a 40-line
traceback per request; the prod compose no longer seeds demo data or prints demo logins by default.

---

## What the carry-over audit found (production-readiness, phase 0)

The independent audit's open findings were re-tested against `main`. Each fix has a test that failed
before it; the rest are guards proven by `scripts/mutate.py` (23 critical-line mutations, all caught).

- **Tenant scoping was correct but unprotected.** Removing team scoping from the services, policies,
  schedules, on-call, timeline and notification lists failed no test. `core/tests/test_tenant_matrix.py`
  now enumerates every route from the URL resolver; the mutation check confirms each scoping line is caught.
- **A layer starting in year 1** was accepted by the API and crashed `/oncall/` and ingest (`OverflowError`).
  Now refused by the API and a `CHECK`, and the resolver skips a layer it cannot evaluate instead of failing.
- **Deleting a schedule or user named only by an open incident's frozen policy** succeeded and left the
  incident escalating to nobody. Now refused (409 `in_use`) while any open incident names it. My first version also guarded queryset and cascade deletes with a `pre_delete` signal and broke the nightly demo reseed (a team wipe removes its incidents in the same cascade), which the existing seed test caught; the guard now covers direct deletes only.
- **Two N+1 endpoints** (schedules list: 8 queries for 1 row, 44 for 13; `/oncalls/`: 11 vs 23) are flat.
- **Alert dropped under sustained churn**: 6 to 7 `ingest_conflict` per run with 8 looping triggers against
  8 looping resolvers. Root cause: a loser of the open race re-read, found nothing open and lost again. A
  per-key advisory lock now serialises open-or-attach; none dropped in repeated runs.
- **Not a bug, but untested**: inactive users are never paged; tasks are enqueued only after commit; the
  incident row lock, the ingest locks and the delivery claim lock. Each now has a test that fails when the
  guard is removed.
- **Method note**: the first mutation run reported a malformed mutation as "caught" because any non-zero
  exit counted. The harness now counts only a real test failure.


## Observability (production-readiness, phase 1)

- **State metrics come from the database at scrape time, not from in-process counters.** Pulse runs
  several gunicorn workers and separate Celery containers; per-process counters of incidents or
  notifications would be wrong or missing. Postgres is already the source of truth (that is the
  whole design), so gauges for open incidents, overdue timers and stuck pages are queries. Only
  request-level metrics (rate, latency, Events API outcomes) are counted in-process, merged across
  gunicorn workers with prometheus_client multiprocess mode.
- **`pending` notifications are a gauge, not part of a counter.** A counter that goes down looks like a
  reset to `rate()`, so only terminal statuses are exposed as `pulse_notifications_total`.
- **The dead-man's switch pings only while healthy.** A heartbeat that fires regardless proves only
  that Celery Beat is alive; gating it on the sweeper and delivery checks makes silence mean "Pulse is
  not paging", which is the thing an operator needs to learn from outside.
- **`/metrics` is off until a token is set**, and is not proxied by nginx. A secure default beats a
  convenient one for an endpoint that reveals incident volume.
- **No gunicorn access log.** The app writes one structured line per request instead, with the route
  template and no query string, so logs stay JSON and cannot capture a key passed in a URL.
- New dependencies: `sentry-sdk` (required to report errors at all; imported only when a DSN is set),
  `prometheus-client` (the standard exposition format and multiprocess aggregation), `@sentry/react`
  (separate chunk, absent from the bundle unless `VITE_SENTRY_DSN` is set at build).


## Data safety (production-readiness, phase 2)

- **Backups are verified before they are trusted, and rotation follows verification.** `backup.sh`
  reads its own dump back and only then prunes older ones. A job that fails every night leaves the last
  good dump alone and stays silent toward the dead-man's switch, which is how the failure gets noticed.
- **The drill compares sequences, not just rows.** A restored database with correct rows and a stale
  sequence would hand out duplicate incident numbers on the first new alert; the drill ends by
  creating one.
- **No point-in-time recovery was built.** WAL archiving is operational machinery that a managed
  Postgres already does better; the honest position is RPO = one backup interval and a pointer to PITR
  if that is not enough.
- **Expand/contract is the migration rule, enforced mechanically where possible.** Dropping or
  renaming a column in the same release that stops using it breaks the old code during a rolling
  deploy. `django-migration-linter` (dev dependency, justified: it is the maintained tool for exactly
  this check and runs only in CI) fails the build on the destructive operations.
- **`migrate_safely` instead of trusting `migrate` to be re-entrant.** Reproduced the failure first
  (3 of 4 concurrent runs crash on a fresh database), then serialised with `pg_advisory_lock`.
- **Retention is opt-in and conservative.** Default keeps everything; only *resolved* incidents past the
  cutoff are removed, never open ones; alerts are deleted explicitly because their FK is `SET_NULL`.
- **Timeouts are deliberate and configurable.** 15 s statements, 5 s lock waits, 60 s idle-in-transaction.
  The idle limit is off in the test settings because pytest-django holds a transaction open for a whole
  test. All three can be set to 0 for poolers that reject startup options.
- **Celery `visibility_timeout` is an explicit 3600 s** rather than an inherited default, with the
  reasoning written next to it: recovery of a dead worker's page does not depend on it.


## Channels (production-readiness, phase 3)

- **Twilio over its REST API, no SDK.** Two form POSTs and a signature check do not justify a
  dependency; `TWILIO_API_BASE` lets the tests talk HTTP to a local fake.
- **Webhooks instead of browser push.** One signed, SSRF-guarded HTTP channel covers Slack, Teams and
  anything a team already has, without VAPID keys, a service worker and per-browser subscriptions.
  Push is listed as not built.
- **Rules snapshot into rows, not into the incident.** Each step becomes a Notification with its own
  `not_before`, so the same claim/settle/sweep machinery that made email safe makes delayed SMS and
  calls safe, and "edit rules later" cannot change a page already made.
- **Permanent vs transient failures.** Before this, every failure retried five times. A bad phone number
  or an unconfigured channel now fails at once, visibly, because retrying a page that cannot succeed
  only delays the moment someone notices.
- **Links act on POST only.** Mail scanners and link unfurlers GET every URL; acting on GET would let
  them acknowledge incidents nobody saw.
- **Found while building it:** `page()` used the wall clock rather than the caller's `now`, so delayed
  steps would have been scheduled from the wrong time under a skewed (or simulated) clock. All four call
  sites now pass `now`.
- **The migration linter caught two real problems in this phase's own migration.** The first draft
  added indexes to the live `notifications` table non-concurrently (a write lock while paging) and
  let Django drop the new columns' defaults (inserts from the previous release would fail during a
  rolling deploy). The columns now keep a database default (`db_default`), the indexes are built
  `CONCURRENTLY` in a separate non-atomic migration, and `test_migration_0004.py` pins that SQL
  because the linter cannot tell a kept default from a dropped one (that one migration is on its
  ignore list, with the reason in `config/settings/lint.py`).


## Security (production-readiness, phase 4)

- **TOTP implemented in ~30 lines rather than a dependency**, pinned by the RFC 4226 and 6238 test
  vectors. Each time step is accepted once (`last_used_step`), which most libraries leave to the caller.
- **The password step does not authenticate.** It parks the user id in the session for five minutes;
  only the code step calls `login()`. A half-finished sign-in therefore has no session to abuse.
- **The Django admin's own login is replaced, not hardened.** Adding MFA to two login forms is twice the
  surface; redirecting the admin to the app's sign-in reuses one path with lockout, MFA and audit.
- **Per-account lockout on top of per-address throttling**, keyed on the attempted email whether or not
  it exists. It makes targeted lockout possible (15 minutes), which is the usual price of stopping
  distributed guessing; recorded here rather than hidden.
- **The audit log is append-only in the database**, by trigger. A rule in application code would not
  survive a bug, a shell session or a SQL injection through the app's role.
- **Hashed integration keys broke the expand/contract rule on purpose.** The plaintext column is dropped
  in the same release (migration 0003), because keeping working credentials for another release is the
  risk being removed. The previous release cannot read keys after the migration, so this one deploys
  with a stop-then-start (senders retry), not a rolling restart. A grace window covers rotations.
- **OIDC/SSO is not built.** Done properly it needs account linking, just-in-time provisioning and a
  decision about MFA (trust the IdP's or not); a half version would be worse than none.
- **Found while doing it:** the nginx config never proxied `/a/`, so the one-tap acknowledge links added
  in phase 3 would have served the SPA in the Docker stacks. Fixed, and `make doctor` now checks it.

## Product and supply chain (production-readiness, phase 5)

- **Tenancy: one organisation per deployment**, stated at the top of the README and in
  [TENANCY.md](TENANCY.md). Teams are the isolation boundary inside it, guarded by the tenant matrix.
  Real multi-tenancy needs an organisation on every row and Postgres row-level security to fail closed.
  That is a cross-cutting change with no payoff for what this project demonstrates, and one deployment
  per organisation isolates more strongly anyway.
- **One error envelope for everything under `/api/`**: 404s for unknown paths, 413s and 500s too. They
  used to be Django's HTML pages, which a client can only treat as "something broke". The 500 names the
  request id the logs carry, never the raw header, and never the exception text.
- **`Idempotency-Key` is a convenience, not a guarantee.** It lives in Redis, scoped per caller, for 24
  hours, and is ignored when Redis is down. Paging correctness stays in Postgres, where it was. Responses
  that carry a one-time secret are `no-store` and leave only a tombstone, so a retry gets 409 rather
  than a second copy of the key.
- **Trivy runs as a checksum-pinned binary, not through its GitHub Action.** In March 2026 the action's
  tags were force-pushed to malicious commits and v0.69.4 was trojaned (CVE-2026-33634). v0.69.3 is an
  immutable release signed before the attack. All other actions are pinned by commit SHA, and Dependabot
  moves the SHA and its version comment together.
- **Lazy routes for everything but the sign-in and incident screens.** The single 269 kB (gzip) bundle is
  now 146 kB on first load. Analytics, and the charting library it pulls in, load only on that page.
  `npm run check:bundle` fails CI over 170 kB initial or 130 kB per chunk, and also fails if a dev-server
  URL or a key-shaped string reaches the bundle.

### What phase 5 found

Recorded before fixing. Each fix has a test that fails without it, and a mutation in
`scripts/mutate.py`.

- **Cursor pagination skipped and repeated incidents.** Incidents opened in the same instant (an alert
  storm) had no tie-breaker, and polling 25 of them returned only 15 to 19 distinct rows. Every list
  now sorts last by its primary key, and a test walks every router list to check it.
- **Bad query parameters crashed or were silently ignored.** `users?team=abc` and
  `schedules/{id}/overrides?since=bad` answered 500. `incidents?status=triggred` and `urgency=bogus`
  returned an empty list, and analytics and the audit log ignored a malformed `team`, so a typo looked
  like "no incidents". One parser (`core/params.py`) now answers 422 naming the parameter.
- **The throttles swallowed every exception**, so an oversized body was logged as "throttle backend
  unavailable" and reached the view. Only cache errors fail open now, and bodies over 1 MiB are refused
  with 413 before any throttle or view reads them.
- **The replay store would have kept secrets.** With an `Idempotency-Key`, the response to creating a
  service, rotating a key, setting up MFA or regenerating backup codes was stored in Redis for 24 hours:
  the plaintext integration key that phase 4 stopped storing in Postgres. Found while writing the API
  docs; fixed before the feature shipped.
- **The images failed their own scan.** nginx ran as root, and the nginx base had 44 fixed-upstream HIGH
  OS packages. The Python base shipped pip's vendored urllib3 and msgpack, which nothing uses, and the
  backup image carried `gosu`, built with an old Go runtime that has a CRITICAL advisory. Now nginx runs
  as `nginx` on 8080, packages are upgraded at build time, and pip and gosu are removed.
- **The dedup index had stopped being tested.** Phase 0 added a per-key advisory lock to ingest, and
  since then that lock alone kept the concurrency test green. Dropping the partial unique index (I1's
  structural guarantee) failed nothing; the full mutation run showed `dedup-index` surviving. A direct
  test now inserts a second open incident for one key and expects `IntegrityError`.

## Deployment (production-readiness, phase 6)

- **The free demo is one container with no Redis and no Celery**, not the full stack with fewer
  replicas. Free tiers give one web process and no background workers. The design already keeps
  every timer and every pending page in Postgres, so the workers' job can be split in two. Work due
  now runs in-process after commit, through the same task code, once, with no retry loop (a task
  called directly re-raises instead of re-queueing). Everything due later is re-driven by
  `POST /internal/tick/`. A missed tick delays work and never loses it, which is the same property
  a lost Celery message already had.
- **The demo ticks itself while it is in use** (after a response has been sent, at most every
  30 s). An external scheduler then only matters while nobody is watching. The 5-minute GitHub
  Actions tick exists but is off until its secrets are set: on a workspace whose free instance-hours
  are shared with other services, keeping the demo awake around the clock would use them all.
- **A public demo needs guarding from its visitors.** The shared `@demo.local` logins can't change
  their password or two-factor settings, and the demo reseeds daily. Without that, one visitor
  turning on MFA would lock everyone else out until the next reset.
- **Rollback is a restart, not a rebuild.** Images are tagged with the release SHA and kept on the
  host, and migrations are never reversed. That is only safe because migrations are expand-only,
  which `lintmigrations` already enforces.

### What phase 6 found

- **Counters assumed Redis's expiry semantics.** The tick's rate limit, the sign-in lockout and
  the password-reset cap used `cache.add(key, 0, timeout)` then `cache.incr(key)`. Redis keeps a
  key's TTL on INCR. Django's database cache implements `incr` as get-then-set, which resets the
  expiry to the 300 s default. On the demo's cache, steady ticks every 6 s therefore held the
  one-minute window open for good: the demo doctor saw 20 of 29 ticks refused and no escalation.
  The 15-minute lockout would also have expired after 5 minutes. `ratelimit.hit` now stores each
  window's start and pins both keys' expiry to its end. `core/tests/test_counters.py` runs on the
  database cache and on locmem; three of its tests failed on the database cache before the fix.

## Polish (production-readiness, phase 7)

- **The README's numbers are measured, not typed.** Each count (invariants, mutations, backend and
  frontend tests, coverage) sits between `<!-- n:name -->` markers. `scripts/readme_numbers.py`
  measures them from the reports CI already produces (pytest's JUnit file and `coverage.xml`,
  Vitest's JSON) and from `docs/INVARIANTS.md` and `scripts/mutate.py`; each CI job fails if the
  figures it measured disagree with the README, and `make readme-numbers` rewrites them. The test
  counts must match exactly; coverage may sit within one point, so a correct change that moves it
  from 95.1 to 94.9 does not fail. The README used to say "96% line coverage"; the figure is now
  the statement-and-branch total that `coverage report` prints and `--cov-fail-under` gates
  (94.9%), which is the number a reviewer re-running the suite would see.
- **The demo GIF and the social preview are recorded from the running app**
  (`scripts/record_demo.sh`), so a UI change can be re-shot in two minutes instead of going stale.
  Frames are Playwright screenshots joined by ffmpeg; Playwright's video recorder needs its own
  ffmpeg build, which a sandbox or CI image may not have.
- **`dump.rdb` stays in history unless the owner decides otherwise.** A Redis snapshot was
  committed in `329163d` and removed (and ignored) in `22ce364`. It holds Celery's queue bindings
  and one unacknowledged `escalate_incident` message for a local seeded incident: no credentials,
  keys or personal data. Purging it would rewrite every later commit and need a force-push of
  `main`, breaking every clone and every PR link for no security gain, so the recommendation is to
  leave it. Rewriting history is the owner's call, not an automated one.
