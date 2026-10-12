# Invariants

What Pulse guarantees, how each guarantee is enforced, and which test proves it.

This is the contract the rest of the repository exists to keep. Every invariant has:

- a **statement** in plain English;
- the **mechanism** that enforces it: a database constraint, a guarded update under a row lock, a pure function, or an idempotency key;
- the **proof**: the test or tests that fail if the invariant breaks.

**Status** says how strong that proof is today:

| Status | Meaning |
|---|---|
| **Enforced by Postgres** | A constraint makes violation impossible; tests show the application copes with it. |
| **Example-tested** | Hand-written tests cover the cases someone thought of. Upgraded below where noted. |
| **Property-tested** | Hypothesis generates the cases (Phase 2: `test_oncall_properties.py`). |
| **Simulated** | Checked after every operation of the seeded fault simulator (`apps/core/invariants.py`, run by `manage.py simulate`). |

Test paths are relative to `backend/apps/`.

| # | Guarantee | Strongest proof today |
|---|---|---|
| [I1](#i1--at-most-one-open-incident-per-service-dedup_key-under-any-concurrency) | One open incident per `(service, dedup_key)`, under any concurrency | Postgres partial unique index |
| [I2](#i2--a-schedule-resolves-to-exactly-one-responder-at-any-instant-or-to-nobody) | A schedule resolves to one member or nobody | Property-tested |
| [I3](#i3--render_shifts-is-a-true-partition-that-agrees-with-on_call) | Rendered shifts partition the window and agree with `on_call` | Property-tested |
| [I4](#i4--no-page-is-ever-duplicated) | One page per responder and step; a send is retried only after a failure | Postgres unique key + guarded update |
| [I5](#i5--no-page-is-ever-lost) | No page is ever lost | Example-tested + simulated |
| [I6](#i6--escalation-terminates) | Escalation terminates | Example-tested + simulated |
| [I7](#i7--no-stuck-timers) | No stuck timers | Example-tested + simulated |
| [I8](#i8--a-non-triggered-incident-never-has-a-live-timer) | Only triggered incidents have a timer | Example-tested + simulated |
| [I9](#i9--first_response_at-is-set-at-most-once-only-by-a-human) | First response is set once, only by a human | Example-tested + simulated |
| [I10](#i10--every-state-transition-writes-exactly-one-timeline-event) | One timeline event per transition | Example-tested + simulated |
| [I11](#i11--daily-and-weekly-handoffs-happen-at-the-configured-local-time-across-dst) | Handoffs at local time across DST | Property-tested |
| [I12](#i12--debug-mode-never-sends-a-page) | Debug mode never sends | Example-tested + simulated |
| [I13](#i13--maintenance-incidents-never-page-and-never-escalate) | Maintenance never pages | Example-tested + simulated |
| [I14](#i14--suppression-windows-are-bounded) | Suppression windows are bounded | Example-tested |
| [I15](#i15--a-failing-channel-gives-up-after-bounded-retries) | Failing channels give up | Example-tested |
| [I16](#i16--teams-are-isolated) | Teams are isolated | Example-tested |
| [I17](#i17--a-policy-edit-never-changes-an-incident-already-in-flight) | Policy edits don't touch in-flight incidents | Example-tested + simulated |
| [I18](#i18--a-later-step-of-a-personal-plan-never-fires-for-an-answered-page) | A later step never fires for an answered page | Example-tested + simulated |
| [I19](#i19--a-later-step-is-never-sent-before-its-time) | A later step is never sent before its time | Example-tested + simulated |

---

## Paging correctness

### I1 — At most one open incident per `(service, dedup_key)`, under any concurrency

Two identical alerts, however they interleave, become one incident with two alerts.

- **Mechanism.** Partial unique index `uniq_open_incident_per_dedup_key` on `(service_id, dedup_key) WHERE status <> 'resolved'`. Ingest first takes a per-key Postgres advisory lock (`core/locks.py::advisory_xact_lock`), so open-or-attach for one `(service, key)` is serialised; it then attaches to an open incident under `SELECT … FOR UPDATE`, or opens one. The unique index is the backstop: a racing insert that still loses gets `IntegrityError` and retries as an attach (`alerting/actions.py::_trigger`). Without the advisory lock, sustained trigger/resolve churn made the loser re-read, find nothing open, insert, and lose again, so two attempts were not enough and alerts were dropped with HTTP 409. A resolved incident frees its key, so a later trigger opens a new incident.
- **Proof.** `incidents/tests/test_dedup_constraint.py` (the index on its own: the advisory lock alone makes the race test pass, so this is what notices the index going missing; mutation `dedup-index`) · `alerting/tests/test_ingest.py::test_concurrent_triggers_with_one_key_create_exactly_one_incident` (8 threads, one key → one incident, 8 alerts) · `test_same_dedup_key_attaches_to_the_open_incident` · `test_trigger_after_resolve_opens_a_new_incident` · `test_dedup_is_scoped_to_the_service` · `alerting/tests/test_ingest_churn.py` (8 looping triggers against 8 looping resolvers: no alert dropped, never two open incidents).
- **Status.** Enforced by Postgres. Example-tested for the attach/retry path. Simulated, with colliding keys under every fault type.

### I4 — No page is ever duplicated

At most one `Notification` row exists per `(incident, level, loop, seq, user, channel)`, and a row is never sent concurrently or again after it is recorded as sent, even if the escalation runs twice, a task is delivered twice, or two sweepers race.

**What this does not promise.** Delivery is *at least once* across failures we cannot observe: a worker that dies after the provider accepted the message but before the row is settled, or a provider that accepts it but answers slower than the timeout, is retried (a pager prefers a repeat to a lost page). The repeats are bounded by `MAX_ATTEMPTS` (5), and a person can receive up to that many copies of one page. The final audit reproduced this live with a mail relay that took 12 s against a 10 s timeout (finding F1, residual risk).

- **Mechanism.**
  1. The idempotency key `incident:{id}:level:{n}:loop:{k}:user:{id}:channel:{c}[:seq:{event}]` encodes exactly that tuple and is `UNIQUE` in Postgres. Rows are created with `get_or_create` on it (`notifications/actions.py::page`).
  2. The engine's guarded query (`escalations/engine.py::escalate`) only matches an incident still triggered, at the expected level and loop, and already due, under `SELECT … FOR UPDATE SKIP LOCKED`. A second caller matches nothing.
  3. Delivery *claims* the row under a row lock (`status = 'pending'` and no fresh `claimed_at`), counts the attempt, commits, and only then sends with no transaction open; a second concurrent worker sees the fresh claim and returns. A claim left by a dead worker expires after `CLAIM_TTL` (60 s) (`notifications/actions.py::deliver`).
- **Proof.** `escalations/tests/test_engine.py::test_eta_task_and_sweeper_double_fire_pages_once` · `test_concurrent_escalations_of_one_incident_page_once` (4 threads) · `notifications/tests/test_delivery.py::test_paging_twice_never_double_pages` · `test_redelivery_of_a_sent_notification_is_a_no_op` · `notifications/tests/test_delivery_claim.py` (two workers racing on one row send once; a fresh claim is respected; a dead worker's claim expires; the send runs with no transaction and no row lock) · `alerting/tests/test_ingest.py::test_duplicates_do_not_page_again`.
- **Status.** Row uniqueness is enforced by Postgres. Never-concurrent and never-after-sent are example-tested; the bounded repeat after an ambiguous failure is pinned by `test_an_ambiguous_timeout_is_retried_so_delivery_is_at_least_once_and_bounded`. Simulated, with tasks executed twice and concurrent sweepers.

### I5 — No page is ever lost

If an escalation step decides to page a reachable responder, a `Notification` row exists for them, whatever the broker did. Once the system drains, every row is delivered, recorded as a dry run, or marked failed after bounded retries; none stays pending forever.

- **Mechanism.** Rows are written in the *same transaction* as the decision to page (open, escalate, unacknowledge, reassign), never by a later task. Enqueueing happens only after commit (`core/dispatch.py::on_commit`), and a broker failure is logged rather than raised. `sweep_stuck_notifications` re-dispatches rows still pending after two minutes. The escalation itself is recovered by the sweeper (I7).
- **Proof.** `escalations/tests/test_engine.py::test_broker_outage_does_not_fail_ingest` · `test_sweeper_recovers_when_the_eta_message_is_lost` · `notifications/tests/test_delivery.py::test_sweeper_redispatches_pending_rows_whose_task_was_lost` · `notifications/tests/test_poison_delivery.py::test_unexpected_error_eventually_marks_failed`. Live: `make chaos-redis`.
- **Status.** Example-tested. Simulated: every paging event's recipients must have rows for that page (`page_key`), always including the inbox entry, since the other channels follow each person's own plan; the drained system must have no pending rows.

### I6 — Escalation terminates

Without human intervention, no incident escalates forever. After at most `levels × (loops + 1)` automatic steps (escalations plus no-responder skips), the timer clears and the incident stays open, visible and quiet.

- **Mechanism.** `escalations/snapshot.py::next_step` walks levels, then loops, and returns `None` after the last level of the last loop; the engine then clears `next_escalation_at` and logs `escalation_exhausted`. The snapshot is frozen, and `num_loops ≤ 3` is a `CHECK` constraint (`policy_num_loops_max_3`). Levels per policy are capped at 10 (`core/limits.py`).
- **Proof.** `escalations/tests/test_engine.py::test_exhausts_after_the_last_level_when_no_loops_remain` · `test_loops_back_to_level_zero_when_loops_remain` · `escalations/tests/test_snapshot.py::test_next_step_walks_levels_then_loops` · `test_next_step_on_an_empty_policy_is_exhausted`.
- **Status.** Example-tested. Simulated: the step count per incident is bounded, and a drained system has no live timers on unattended incidents.

### I7 — No stuck timers

A triggered incident with a non-null `next_escalation_at` always makes progress when it is due. The next sweep either moves it to a valid next step or clears the timer. A level with nobody on call doesn't wait out its delay: it is due again immediately.

- **Mechanism.** The sweeper selects every `status = 'triggered' AND next_escalation_at <= now` (`escalations/engine.py::due_incidents`) and calls the guarded `escalate`, which either advances (`apply_level`) or clears the timer (exhausted). An empty level sets `next_escalation_at = now` (high urgency) instead of `now + delay`. An empty policy never sets a timer at all.
- **Proof.** `escalations/tests/test_engine.py::test_no_responder_moves_to_the_next_level_on_the_next_sweep` · `alerting/tests/test_ingest.py::test_ingest_without_a_policy_target_still_records_the_incident`.
- **Status.** Example-tested. Simulated: after every sweep, each incident that was due has advanced or cleared.

### I8 — A non-triggered incident never has a live timer

`status <> 'triggered'` implies `next_escalation_at IS NULL`.

- **Mechanism.** `acknowledge` and `resolve` clear the timer in the same locked update that changes the status (`incidents/actions.py`). Every path back to `triggered` (unacknowledge, reassign, manual escalate) sets it from the snapshot. The engine only touches incidents whose guarded query requires `status = 'triggered'`.
- **Proof.** `escalations/tests/test_engine.py::test_ack_stops_escalation` · `incidents/tests/test_state_machine.py::test_resolve_resolves_attached_alerts_and_clears_the_timer` · `alerting/tests/test_ingest.py::test_acknowledge_event_by_dedup_key`.
- **Status.** Example-tested. Simulated after every operation. (A database `CHECK` would make this structural; it is a candidate for a follow-up migration once the simulator has confirmed no code path violates it.)

### I9 — `first_response_at` is set at most once, only by a human

It is set by the first human acknowledge, unacknowledge, resolve, reassign or manual escalate, and never changed afterwards. Source-driven events (the monitor acknowledging or resolving) and notes never set it.

- **Mechanism.** One place, `incidents/actions.py::_transition`: only when `actor is not None`, the action is in `FIRST_RESPONSE_ACTIONS`, and the field is still null. Events API transitions pass `actor=None`.
- **Proof.** `incidents/tests/test_state_machine.py::test_first_response_is_set_once_by_the_first_human_action` · `test_every_human_action_counts_as_first_response` (parametrised over all five) · `alerting/tests/test_ingest.py::test_acknowledge_event_by_dedup_key` · `test_resolve_event_by_dedup_key` · `analytics/tests/test_analytics.py::test_source_driven_resolves_do_not_count_as_first_response`.
- **Status.** Example-tested. Simulated: once set it never changes, and it always equals the time of a human first-response event.

### I10 — Every state transition writes exactly one timeline event

Each incident action (acknowledge, unacknowledge, resolve, reassign, manual escalate, add note) and each automatic escalation step writes exactly one `IncidentEvent`. Delivery receipts (`notified`, `notification_failed`) are recorded separately, and an attached duplicate alert writes one `alert_attached`. Opening an incident writes `triggered` (or `maintenance_started`), plus `no_responder` if level 1 is empty.

- **Mechanism.** Each action in `incidents/actions.py` and each branch of `escalations/engine.py::escalate` calls `timeline.record` exactly once, inside the same transaction as the state change, so the event and the change commit or roll back together.
- **Proof.** `incidents/tests/test_state_machine.py::test_transition_table_is_enforced` (every action × every status: each allowed transition adds exactly one non-delivery event; each forbidden one raises `InvalidTransition` inside the transaction, so nothing commits).
- **Status.** Example-tested. Simulated: event deltas are checked against every operation's outcome.

---

## On-call correctness

### I2 — A schedule resolves to exactly one responder at any instant, or to nobody

The answer is always one user who is a member of the schedule's layers or overrides, or nobody, never two and never a stranger. The answer is deterministic: same inputs, same answer.

- **Mechanism.** `schedules/oncall.py` is pure functions over frozen dataclasses: no database, no clock. `on_call` returns a single `int | None`: the covering override with the highest `seq` (the loader sets `seq` to the row's primary key, i.e. creation order), else the first layer by descending priority that yields a member, else `None`.
- **Preconditions.** The instant is timezone-aware, custom layers have a positive turn length, and a layer starts between 2000 and 2100. Both are `CHECK` constraints (`layer_turn_length_positive`, `layer_start_in_range`) and API validation; before, a layer starting in year 1 was accepted, then raised `OverflowError` from `/oncall/` and from Events ingest. If bad data ever reaches the resolver it skips that layer and logs an error instead of failing the page (`schedules/tests/test_layer_start_bounds.py`). Determinism treats the host's tz database as an input: hosts with different tzdata versions can disagree on future transitions.
- **Proof.** `schedules/tests/test_oncall.py::test_override_beats_every_layer` · `test_latest_created_override_wins_when_overrides_overlap` · `test_highest_priority_layer_with_someone_on_call_wins` · `test_empty_high_priority_layer_falls_through` · `test_schedule_with_no_layers_has_nobody_on_call`.
- **Property tests.** `schedules/tests/test_oncall_properties.py::test_on_call_is_a_member_or_nobody` · `test_on_call_is_deterministic_and_independent_of_input_order` · `test_overrides_and_layer_priority_follow_the_specification` · `test_a_covering_override_always_wins` · `test_rotation_is_round_robin_over_n_turns`. Regression: `schedules/tests/test_oncall.py::test_database_rejects_a_non_positive_custom_turn_length`.
- **Status.** Property-tested over generated schedules in six zones (incl. Lord Howe's 30-minute DST and Chatham's +12:45), across 2025–2027.

### I3 — `render_shifts` is a true partition that agrees with `on_call`

Over `[since, until)`, rendered shifts are contiguous where someone is on call, never overlap, cover every instant at which someone is on call, and agree with `on_call(at)` at every instant inside them. The UI timeline, the `/shifts` endpoint and the escalation engine therefore can't disagree.

- **Mechanism.** `render_shifts` collects every instant where the answer *could* change (layer starts, handoffs, override edges), evaluates `on_call` once per segment and merges equal neighbours. Handoffs inside a DST gap are placed by `_first_instant_of_shift_day`.
- **Proof.** `schedules/tests/test_oncall.py::test_render_shifts_splits_at_handoffs` · `test_render_shifts_merges_equal_neighbours` · `test_render_shifts_cuts_around_overrides` · `test_render_shifts_leaves_gaps_where_nobody_is_on_call` · `test_render_shifts_follows_local_handoffs_across_dst` · `test_render_shifts_handles_a_handoff_inside_the_dst_gap`.
- **Property tests.** `schedules/tests/test_oncall_properties.py::test_render_shifts_is_a_partition_that_agrees_with_on_call` (probes every shift edge, midpoints, random instants, and every 5 minutes for 90 minutes around each DST transition in the window) · `test_on_call_only_changes_at_shift_boundaries`.
- **Status.** Property-tested. These found a real defect: see I11.

### I11 — Daily and weekly handoffs happen at the configured local time, across DST

For daily and weekly rotations, every handoff lands at the layer's local `handoff_time` in the schedule's zone, on both sides of every DST transition. Where that wall time doesn't exist (spring-forward gap), it is the first instant after it. Custom rotations are absolute by design and exempt.

- **Mechanism.** Turns are counted in local calendar days, not elapsed seconds. Shift day D begins at `_first_instant_of_shift_day(D)`, the first instant whose local wall time reaches D `handoff`, and `_shift_day(at)` is the latest day whose begin instant is at or before `at`. Instants are compared, never wall-clock times.
- **Defect found by the property tests.** Previously `_shift_day` compared wall-clock times (`local.time() >= handoff`). After a fall-back the same wall time happens twice, so with a 01:30 handoff in New York the second pass through 01:00–01:29 (06:00–06:29 UTC on 2025-11-02) was classified as *before* the handoff: the pager went back to yesterday's responder for 30 minutes, while the rendered timeline (correctly) showed today's. Fixed by defining the shift day by instants.
- **Proof.** `schedules/tests/test_oncall.py::test_dst_spring_forward_keeps_the_local_handoff_time_in_new_york` · `test_dst_fall_back_keeps_the_local_handoff_time_in_new_york` · `test_dst_transitions_in_london` · `test_render_shifts_handles_a_handoff_inside_the_dst_gap`.
- **Property tests.** `schedules/tests/test_oncall_properties.py::test_daily_and_weekly_handoffs_land_on_the_local_handoff_time_across_dst` (every rendered handoff is at the local handoff time on its first occurrence, or at the end of a DST gap; the resolver agrees with the rendering around every transition). Regressions: `schedules/tests/test_oncall.py::test_fall_back_repeated_hour_does_not_hand_the_pager_back_to_yesterday` · `test_fall_back_repeated_hour_in_london_and_render_agree`. Both fail against the pre-fix resolver.
- **Status.** Property-tested.

---

## Suppression, isolation and bounds

### I12 — Debug mode never sends a page

A service in debug mode runs the whole pipeline (incident, escalation, timeline), but every notification is recorded as a dry run and never sent. That holds even if the mode switches to debug after a page was queued.

- **Mechanism.** `notifications/actions.py::page` creates `dry_run` rows for a debug service; `deliver` re-checks the service mode under the row lock before sending.
- **Proof.** `escalations/tests/test_engine.py::test_debug_mode_runs_the_pipeline_but_only_records_dry_runs` · `notifications/tests/test_delivery.py::test_switching_to_debug_after_paging_still_never_sends`.
- **Status.** Example-tested. Simulated with the mode flipped mid-flight.

### I13 — Maintenance incidents never page and never escalate

In maintenance mode every alert folds into one low-urgency incident per service, with no notifications and no timer. It resolves when the window ends.

- **Mechanism.** `alerting/actions.py::_trigger` routes to the reserved `__maintenance__` dedup key. `incidents/actions.py::open_incident` returns before `apply_level`/`page` for maintenance incidents. `notifications/actions.py::page` refuses maintenance incidents outright, so no human action (unacknowledge, reassign) can page, and manual escalate on one is a `Conflict`. `catalog/actions.py::expire_service_modes` ends the window.
- **Proof.** `alerting/tests/test_ingest.py::test_maintenance_consolidates_every_alert_into_one_quiet_incident` · `test_human_actions_on_a_maintenance_incident_never_page` · `test_mode_expiry_returns_service_to_active_and_closes_maintenance`; `core/invariants.py` checks it after every simulated operation.
- **Status.** Example-tested and simulated. The simulator found that the first version held only until someone clicked a button (see DECISIONS, S1).

### I14 — Suppression windows are bounded

Maintenance and debug both stop real pages, so a window must have an end, at most 24 hours ahead, and it expires automatically. A service can't be silenced indefinitely by accident.

- **Mechanism.** `catalog/serializers.py::ServiceModeSerializer.validate` requires `until` for non-active modes and enforces `MAX_MODE_WINDOW_HOURS` (`core/limits.py`). `expire_service_modes` runs every 60 s.
- **Proof.** `catalog/tests/test_mode_window.py` (all four tests) · `alerting/tests/test_ingest.py::test_mode_expiry_returns_service_to_active_and_closes_maintenance`.
- **Status.** Example-tested at the API boundary. The domain action `set_mode` itself accepts any window; the bound is an API-input rule.

### I15 — A failing channel gives up after bounded retries

A notification that keeps failing, with any exception type, is retried with backoff and then marked `failed` with a `notification_failed` timeline event. It is never re-driven forever.

- **Mechanism.** `notifications/actions.py::deliver` counts every exception as an attempt (the count is committed at claim time, before the send) and re-raises after settling. At `MAX_ATTEMPTS` the row becomes `failed`. `redispatch_stuck` skips rows that have exhausted their attempts.
- **Proof.** `notifications/tests/test_delivery.py::test_transient_failures_retry_then_fail_permanently` · `notifications/tests/test_poison_delivery.py` (all three tests).
- **Status.** Example-tested.

### I16 — Teams are isolated

A user sees and acts only on the services, policies, schedules and incidents of teams they belong to. Viewers can read but not act, responders can act on incidents, and admins can change configuration. Anonymous callers get nothing.

- **Mechanism.** List querysets are filtered by membership (`core/views.py::scope_to_teams`, `incidents/selectors.py::visible_incidents`). Object permissions are ranked by role in one module (`core/permissions.py`). Every permission class re-asserts authentication.
- **Proof.** `core/tests/test_tenant_matrix.py` walks the real URL table, so a new endpoint cannot be added without being classified: every route and method is hit as a member of another team (403/404 and no change for object routes, no leak in collection responses, no creating into the other team) · `core/tests/test_tenant_isolation.py` (13 cases) · `core/tests/test_health.py::test_every_api_endpoint_requires_authentication` · `incidents/tests/test_incidents_api.py::test_viewers_see_no_actions_and_cannot_act` · `test_outsiders_get_404_not_403`.
- **Status.** Example-tested.

### I17 — A policy edit never changes an incident already in flight

Levels, delays, loop count and target identities are frozen when the incident opens. People are not frozen: schedule targets resolve to whoever is on call when each level fires.

- **Mechanism.** `escalations/snapshot.py::build_snapshot` at open; the engine reads only `incident.escalation_snapshot`.
- **Deletion guard.** A frozen policy can still name a schedule or user that was later edited out of the live policy. `escalations/guards.py` refuses a direct delete of either while an open incident names it (HTTP 409 `in_use`) by wrapping `Model.delete`, which the API and `obj.delete()` use. Queryset and cascade deletes are not guarded on purpose: removing a team deletes its incidents in the same cascade (`seed_demo --reset` relies on it), and a `pre_delete` signal cannot tell those cases apart. The admin's bulk "delete selected" action is such a queryset delete, so it is unguarded. A *deactivated* user is never paged (`engine.resolve_targets`), tested in `escalations/tests/test_inactive_responders.py`.
- **Proof.** `escalations/tests/test_engine.py::test_policy_edit_does_not_change_open_incident` · `test_schedule_targets_resolve_to_whoever_is_on_call_when_the_level_fires` · `escalations/tests/test_snapshot_references.py` (5 tests, incl. a whole-team removal that must still work).
- **Status.** Example-tested. Simulated with policies rewritten mid-flight.

---

## Delivery

### C1 — No page is delivered for an incident that is already resolved

If delivery is delayed (broker outage, retries), a page queued before resolution never reaches anyone after the incident is resolved.

- **Mechanism.** `notifications/actions.py::deliver` re-reads the incident under the row lock and marks the notification `cancelled` instead of sending when the incident is resolved.
- **Proof.** `notifications/tests/test_delivery.py::test_a_page_queued_before_resolution_is_never_sent_after_it`; the simulator resolves incidents with undelivered backlogs (`resolve_backlog`) and fails on any send for a resolved incident.
- **Status.** Enforced and simulated. This was a real defect (DECISIONS, S2).

---

### I18 — A later step of a personal plan never fires for an answered page

A step with a delay exists to chase an unanswered page. Once anyone acknowledges (or resolves) the
incident, no later step of anyone's plan is delivered.

- **Mechanism.** `incidents/actions.py::acknowledge` cancels pending delayed steps for the incident in
  the same transaction; `notifications/actions.py::_claim` re-checks under the row lock and cancels any
  delayed step whose incident is not triggered (the guard is the rule, the eager cancel an
  optimisation). Resolve is covered by C1.
- **Proof.** `notifications/tests/test_rules.py::test_acknowledging_cancels_the_later_steps_but_not_the_ones_already_due` ·
  `test_a_late_step_is_cancelled_at_claim_time_even_if_the_ack_missed_it` · `test_resolving_cancels_a_pending_step_too`;
  the simulator fails on any send of a delayed step for a non-triggered incident. Mutation
  `step-cancel-on-ack` is caught.
- **Status.** Enforced and simulated.

### I19 — A later step is never sent before its time

- **Mechanism.** The row carries `not_before`; `_claim` returns without claiming (and without counting
  an attempt) while `now < not_before`, so an early, duplicated or skewed task is harmless.
  `redispatch_stuck` ignores steps that are not yet due.
- **Proof.** `test_rules.py::test_a_delayed_step_is_not_sent_early_and_is_sent_once_due` ·
  `test_a_lost_eta_message_is_recovered_by_the_stuck_sweep_once_the_step_is_due`; simulated (fails on
  any send before `not_before`). Mutation `step-not-before` is caught.
- **Status.** Enforced and simulated.

---

## Not mechanically checked

- **Email actually arrives.** Pulse can only prove that it handed a message to the email backend; inbox delivery is outside the system.
- **Clock accuracy.** Due times are computed and compared with the clock of whichever app or worker process acts, so timing assumes NTP-synchronised hosts. A worker whose clock runs ahead escalates early by that skew; one that runs behind is caught up by any other worker's sweep. Skew can shift *when* a step happens, but the guarded update means it can't make a step happen twice (I4) or be skipped (I7). The simulator injects small skews (`skewed_sweep`).
