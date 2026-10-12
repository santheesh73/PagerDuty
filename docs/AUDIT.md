# Final audit

An independent audit of Pulse before calling it production-ready, run by five reviewers who each worked from a fresh clone and were told to find what is wrong, with evidence, not to fix it. The author (an AI assistant, not a human team) then re-verified the High findings, fixed what was fixable with a regression test that fails on the old code, and recorded the rest here.

**This is a self-assessment with independent reviewers, not a third-party audit.** The reviewers were instances of the same model family as the author. Nothing here was checked by a person outside this repository's owner, and Docker was not available in the audit environment, so every Docker-based claim rests on CI.

## Verdict

**No Critical and no High findings remain.** The one finding first rated High (a slow mail relay can repeat a page up to five times) is re-rated Medium below, with the reasoning.

The core guarantees held under attack: no cross-team data leaked in 534 authorisation probes and every list and object route, a 420,714-point independent oracle found no DST or rotation error, 8-way concurrent alerts made one incident, and no run of the load test produced a duplicate page.

What the audit did find was real, and some of it was embarrassing:

- a backup script that failed on every day except Sunday (CI and every earlier run had happened to run on a Sunday);
- a sign-in rate limit that did not apply to anyone who already held a session, and a second-factor limit that reset with each password step;
- a lock-order deadlock that could make a human's acknowledge fail with a 500;
- a notification that could stay `pending` forever;
- thirteen security-relevant lines that no test would have noticed being removed.

All of these are fixed (see [findings](#findings)). Eleven Medium and several Low findings remain open, listed under [residual risk](#residual-risks). **Pulse is a well-tested, honestly documented system that is ready to run a small deployment. It has not been run in production**, and the public demo is not yet deployed (it needs a database URL only the owner can supply).

### Grades

| Area | Grade | Why |
|---|---|---|
| Correctness | **B** | Invariants I1, I2, I3, I6 to I11, I17, I19 held under independent attack. I4 (single delivery) and I13 (maintenance never pages) are narrower than they were written; I5 was broken by one path, now fixed. A maintenance-expiry race still swallows an alert (open). |
| Security | **B** | No authorisation, injection, SSRF or secret finding of consequence; strong tenancy, CSRF, MFA, signed-link and SSRF guards. Lost points for the throttle bypass and `NUM_PROXIES` default (fixed), the demo's shared-login leaks (fixed), and open Low items such as the reset-timing oracle and a truncatable audit log. |
| Tests | **B** | 694 backend tests at 95% statement and branch coverage, a 94-mutation harness, property tests, a fault-injection simulator. The mutation work found 13 unpinned guards (now pinned). Frontend coverage is 31% with no threshold, and the mutation harness does not run in CI. |
| Architecture | **B** | Postgres as the source of truth, DB-as-timer and claim/send/settle delivery are sound and survived Redis loss, Beat loss and connection loss. The lock-order deadlock and the missing incident-list index show where it was not yet exercised. |
| Operability | **C** | Drills passed (Beat, SMTP, Redis, Postgres, disk full), alerts fire, backups restore. But detection is slow (a dead Beat is flagged in about 4 minutes), a lost Redis plus a dead Beat blinds the Beat alert, the email retry budget is only about 17 s, and failed pages are hard for an operator to see. |
| Docs honesty | **B** | The claims were mostly true (102 of 122 ledger rows). The false ones were stale numbers and one overclaim ("at most once"), all corrected. |
| Portfolio polish | **B** | Clear README with measured numbers, a recorded demo, runbooks. Not deployed, so no live link. |

## How it was done

| Track | Scope | Clone |
|---|---|---|
| Security | authorisation matrix, IDOR, secrets, dependencies, headers, SSRF, replay, authentication | `eb50b24` |
| Operations | drills without Docker, alert rules, load test | `eb50b24` |
| Mutation | the harness, extra mutations, test quality, a past flaky test | `eb50b24` |
| Review | invariant-by-invariant attack on the engine, API, demo mode, architecture | `eb50b24` |
| Build and claims | every gate a contributor or CI runs, a ledger of documentation claims | `5fa1e9e` |

`5fa1e9e` differs from `eb50b24` only in docs, CI, scripts and images (no application code), so the five tracks audited the same application. Fixes are in [PR 27](https://github.com/santheesh73/PagerDuty/pull/27).

The reviewers ran on a 4-vCPU Linux sandbox with PostgreSQL 16 (CI uses 17) and no Docker daemon, and shared the machine while running. Their raw artefacts (probe tests, logs, scanner reports) were not committed; the evidence below is reproducible with the commands in [How to reproduce](#how-to-reproduce).

## Commands and results

### Gates

| Command | Result |
|---|---|
| `ruff check`, `ruff format --check`, `mypy .` | pass (138 files) |
| `makemigrations --check`, `lintmigrations` | pass; 17 migrations (14 valid, 2 ignored, 1 warning: a plain `CREATE INDEX` in `catalog/0002`) |
| `spectacular --validate`, diff against `openapi.yaml` | identical |
| `pytest --cov --cov-fail-under=85` | 653 passed at audit start; **694 passed** after the fixes; 94.9% statement and branch coverage |
| `readme_numbers.py --check` | passes (and fails on each kind of drift, shown when it was added) |
| Frontend `lint`, `format:check`, `typecheck`, `test`, `build`, `check:bundle` | pass; 42 tests; initial JS 146 kB gzip (budget 170) |
| `manage.py simulate --seeds 20 --operations 600` | seeds 1 to 20 pass (651 s) |
| `backup_drill.sh` | 31 tables, 407 incidents, 114 indexes, 115 constraints and all sequences identical; API boots on the restored copy. **Passed on a Sunday, which hid the backup bug**; passes on a Monday in CI after the fix |
| One-container demo without Docker, `doctor.py --demo` | 26 passed, 0 failed (escalation driven by ticks alone) |
| Playwright against the demo | 2 passed (accessibility audit, alert-to-resolve journey) |
| `smoke.sh` against the demo | 13 PASS |
| `shellcheck` (CI's files), `actionlint` | pass |
| `check --deploy --fail-level WARNING` (production settings) | no issues (2 silenced by design) |
| `pip-audit --strict`, `npm audit` (frontend, e2e), Trivy fs (vuln, secret, misconfig) | 0 findings |
| gitleaks and trufflehog over the full history including pull refs | no secrets; every trufflehog hit a documented false positive |
| CI on `main` at `5fa1e9e` | all 9 jobs green, including `docker-smoke` (42 checks), `demo-doctor` (38), E2E and backup drill |

### Security checks (all with evidence from the security track)

| Check | Result |
|---|---|
| Authorisation matrix, 534 requests, 6 principals | 532 match the role model; 2 mismatches (overrides answered 403 instead of 404), now fixed |
| IDOR on every detail, update, delete and action route using another team's ids | 404 (incident status never changed) |
| Cross-team ids inside request bodies, forged cursors, mass assignment (`is_staff`) | refused or ignored |
| CSRF on all 44 unsafe routes × 3 principals | 132 of 132 refused without a token |
| MFA: password-only step, TOTP replay, backup-code reuse, disable without re-auth, admin enrolment gate | all enforced |
| Session fixation and logout invalidation | session id rotates at both steps; old cookie refused after logout |
| One-tap action links: reuse, tamper, expiry, ex-member, resolved incident | all refused or non-spending as designed |
| Twilio signature: missing, wrong, other URL, extra field | refused; an exact replay is accepted (inherent to the scheme; state is monotonic) |
| Integration keys | stored only as a SHA-256 and an 8-character prefix |
| SSRF: 36 address forms incl. decimal, octal, IPv6-mapped, NAT64, Teredo; mixed DNS answers; rebinding; redirects | all refused; the validated address is the one connected to (DNS was simulated, see NOT VERIFIED) |
| Headers and cookies | HSTS one year, CSP, frame-ancestors, nosniff, COOP, `__Host-` session cookie (HttpOnly, Secure, Lax) |
| Raw SQL, `pickle`, `eval`, `mark_safe` | only parameterised or constant SQL |

### Operational drills (host processes, production settings, no Docker)

| Drill | Observed | Verdict |
|---|---|---|
| Kill Beat | metric stale at once; `PulseBeatStalled` firing about 3 min 54 s later; `selfcheck` exits 1; outbound dead-man's ping stops | pass (slow, see M-13) |
| Page while Beat is down | level 1 sent; the ETA task escalated to level 2 on time | pass |
| Overdue escalation, Beat down, then restarted | caught up in about 1 s; exactly one email, distinct keys | pass |
| SMTP down | 5 attempts in 17 s, row `failed`, event and metric recorded, alert firing, no duplicate when SMTP returned | pass (short budget, see M-12) |
| SMTP returns mid-retry | one email | pass |
| Disk full during backup (1 MiB tmpfs) | non-zero exit, no heartbeat, `.partial` removed, last good backup intact and restorable; the weekly copy left a truncated dump | partial; fixed |
| Redis `FLUSHDB` mid-incident | escalation continued, 0 duplicate keys, heartbeat absent about 44 s | pass |
| Postgres connections killed, then refused | reconnects transparently; `/readyz` 503 and `/healthz` 200 while refused; recovers in under 1 s | pass |
| `promtool check rules`, every alert's metric exported, a synthetic fire-and-resolve test for all 14 alerts | pass | pass |

### Load (k6 2.3.0, 3 gunicorn workers, 30% new keys, `THROTTLE_EVENTS=100000/min`)

| VUs | req/s | p50 ms | p95 ms | p99 ms | errors | database invariants |
|---|---|---|---|---|---|---|
| 1 | 31 | 26 | 68 | 90 | 0% | hold |
| 4 | 66 | 54 | 118 | 152 | 0% | hold |
| 8 | 68 | 110 | 208 | 292 | 0% | hold |
| 16 | 42 | 372 | 574 | 658 | 0% | hold |
| 32 | 66 | 467 | 746 | 820 | 0% | hold |
| 64 | 50 | 1281 | 1682 | 1754 | 0% | hold |
| 128 | 47 | 3032 | 3587 | 3697 | 0% | hold |

**Degradation point:** throughput saturated at about 65 requests/s from 4 virtual users; p95 passed 500 ms between 8 and 16. There was no cliff and no errors, only queueing. The limit is CPU (gunicorn, Postgres and the Celery workers shared four cores with the other reviewers' jobs), not the database connection pool (11 to 12 of 100 used) or the throttle. Eight workers did worse than three on this host. **These figures are a lower bound on a contended machine, not a capacity claim.** At every step the verifier found one incident per new key, no duplicate page, and emails equal to email rows.

## Findings

Severity: **Critical** a page lost or doubled, cross-team exposure, auth bypass, RCE or a leaked secret under realistic conditions. **High** a written guarantee broken under realistic conditions, an exploitable weakness, or an ops path that loses data silently. **Medium** degraded behaviour or a defence-in-depth gap. **Low** minor.

### Critical: none. High: none.

**Re-verification of the one finding first rated High.** The review track reported (live, demo mode) that a mail relay which acknowledges `DATA` after 12 s with a 10 s `EMAIL_TIMEOUT` made one page arrive five times, then recorded it as failed. I reproduced the mechanism with a fake channel that "delivers" and then raises a timeout: five sends, then `failed` (`test_an_ambiguous_timeout_is_retried_so_delivery_is_at_least_once_and_bounded`). This is the standard at-least-once trade-off: a timeout after the message is accepted cannot be told from a failure, and a pager should prefer a repeat to a lost page. It needs a relay slower than the timeout, the repeats are bounded by `MAX_ATTEMPTS`, and the in-app and next-level paths are unaffected. I re-rated it **Medium**. The real defect was the documentation, which promised "at most once"; I4 now says what it does (see M-9).

### Fixed (each has a regression test that fails on the old code unless noted)

| # | Sev | Finding | Fix |
|---|---|---|---|
| F-1 | Med | `scripts/backup.sh` exited 2 on every day except the weekly one until the first weekly copy existed, skipping the off-site upload and heartbeat | prune tolerates an empty directory; `test_a_first_backup_succeeds_whatever_the_weekday` |
| F-2 | Med | Weekly backup copy was an unchecked `cp`: a full disk left a truncated dump under its final name, which retention then kept in place of a good one | copy to a partial name, then `mv`; `test_a_weekly_copy_that_fails_halfway_...` |
| F-3 | Med | Sign-in, MFA-code and reset throttles skipped anyone already signed in; wrong codes were only capped per password step, so a signed-in user who knew a password could guess a TOTP code without limit | address throttles regardless of session; per-account lockout after 10 wrong codes in 15 minutes; `test_sign_in_limits.py` (the live brute-force path was reviewed by reading the code, not run) |
| F-4 | Med | Unset `NUM_PROXIES` trusted the whole `X-Forwarded-For`, so a client chose the address its limits and audit log saw; `deploy/render-full.yaml` left it unset | required by production settings; set in the blueprint (value derived from the topology, **unverified**: check with the procedure in `docs/DEPLOY.md`); doctor and unit test now use a different account per attempt, because the old check was satisfied by the account lockout alone |
| F-5 | Med | `/api/docs/` loaded `swagger-ui-dist@latest` from a CDN, with no integrity check, on the origin that holds the session cookie | off in production unless `API_DOCS=1`; version pinned when on (no SRI; self-hosting would remove the CDN) |
| F-6 | Med | Demo: visitors sharing a login saw each other's IP address and browser, and could sign each other out; the full-stack Render blueprint had no guard at all | `DEMO_ACCOUNT_GUARD` redacts and blocks; set in the blueprint |
| F-7 | Med | An acknowledge could abort with "deadlock detected" (HTTP 500, 5 of 5 forced interleavings): delivery settle and acknowledge took the notification and incident locks in opposite orders | incident rows are locked `FOR NO KEY UPDATE`; `test_an_acknowledge_during_a_delivery_settle_does_not_deadlock` |
| F-8 | Med | A notification whose worker died after its last claim stayed `pending` forever (both sweepers skipped rows at the attempt cap), breaking I5 | sweepers include rows at the cap, so `deliver` fails them and records the event |
| F-9 | Med | A hung (accepting but silent) Redis blocked every request that enqueues for minutes after the incident had committed | broker socket and connect timeouts and a one-retry publish policy (settings asserted; a full gunicorn brown-out was not reproduced) |
| F-10 | Med | Demo: the database cache culled a third of its rows at 300 entries, including the daily-reset guard and the lockout counters, so the next tick could wipe the public demo | `MAX_ENTRIES` raised |
| F-11 | Low | Another team's schedule overrides answered 403 (an id-existence oracle); the tenant matrix accepted 403 or 404 | matrix now requires 404; lookup scoped to the caller's teams |
| F-12 | Low | Six query forms (`since=2026-02-30`, `+25:00`, `until=…T25:00`, year 1 and 9999 windows) returned 500 | 422 naming the parameter |
| F-13 | Low | Mailpit (no authentication, holds reset and ack links) published on `0.0.0.0:8025` in two compose files | bound to `127.0.0.1` |
| F-14 | Med | Thirteen security-relevant lines could be removed without any test failing: idempotency while a request is in flight and across routing keys, the `UNIQUE` page key, the claim's row lock, the integration-key prefix, HSTS, every session-cookie flag, count-only scoping of the incidents-per-day chart and the session list | tests and mutations added (below) |
| F-15 | Low | Docs: stale drill and migration figures, missing `cancelled` status, I5's "two minutes" (it is 90 s), decision 18's HSTS default (documented 0, actually one year), the "23 mutations" count, "at most once" | corrected |

### Open (not fixed)

| # | Sev | Finding | Why it is open |
|---|---|---|---|
| M-9 | Med | **At-least-once, not at-most-once.** A worker dying between the provider accepting a message and the row being settled, a relay slower than `EMAIL_TIMEOUT`, or a send longer than `CLAIM_TTL` can repeat a page, up to `MAX_ATTEMPTS` (5) times; the row can then read `failed` for a page that arrived | Inherent to preferring repeats over loss. Documented in I4 and pinned by a test. A fix would treat a timeout after `DATA` as "possibly sent" |
| M-10 | Med | An alert arriving exactly as a maintenance window ends can be absorbed into a new maintenance incident on an active service: it never pages and nothing closes it (I13, I5) | Reproduced by the review track with a controlled interleaving; the fix (re-read the mode after taking the lock) needs its own design and test |
| M-11 | Med | Demo-mode database-cache counters lose increments under concurrency (16 hits counted as 2 to 5; 13 of 30 parallel tick calls allowed against a limit of 12) | Demo only; the shipped demo is single-purpose and the tick is also protected by a secret |
| M-12 | Med | Email retry budget is about 17 s (five quick attempts); an SMTP outage of 20 s or more permanently fails the email page. The in-app page and escalation are the fallback | Needs a time-based retry design |
| M-13 | Med | Beat death is flagged in about 4 minutes (`> 180` for `1m`), and the docs say 3. Only an empty-level escalation depends on the Beat sweeper; the ETA task covers the normal case | Detection speed is a trade-off with false alarms |
| M-14 | Med | A lost Redis plus a dead Beat leaves the heartbeat series absent, so `PulseBeatStalled` cannot fire; only `PulseBeatNeverSeen` does, after 10 minutes (proved with a promtool test) | Persist the heartbeat in Postgres |
| M-15 | Med | Failed pages are hard to see: the API returns only a user's own in-app rows and `last_error` is in no serializer; an operator needs the admin or a shell | Needs an API design |
| L-1 | Low | Filters and request fields naming another team's id (`?team=`, `?escalation_policy=`, `team` in a POST) answer differently for existing and unknown ids | Documented in TENANCY.md |
| L-2 | Low | Password-reset timing differs for known and unknown emails (median 10.5 ms vs 6.5 ms over 200 pairs) | Rate limited (10/h per address, 3/h per email) |
| L-3 | Low | The audit log trigger blocks `UPDATE` and `DELETE` but not `TRUNCATE`, and the app role owns the table | Needs a non-owner role |
| L-4 | Low | Idempotency replays stored 4xx for 24 h including 429; a write can run twice in a two-round-trip race; the query string is not in the key | Documented residual |
| L-5 | Low | The reserved `__maintenance__` dedup key is accepted from monitors | |
| L-6 | Low | A user removed from a team keeps being paged by that team's rotations (action links do re-check membership) | |
| L-7 | Low | A CSRF failure on login returns Django's HTML 403, not the error envelope | |
| L-8 | Low | `PulseNotificationFailures` can false-fire after a retention purge (the metric is a row count) | |
| L-9 | Low | `restore.sh` refuses to overwrite the live database only when the two URLs are spelled identically (`localhost` vs `127.0.0.1` passes) | |
| L-10 | Low | The concurrent-migrate test's cleanup can fail for a non-superuser role (`DROP DATABASE … WITH (FORCE)` cannot signal an autovacuum backend). CI uses a superuser. This is the cause of the once-seen local failure | |
| L-11 | Low | The `ip` shown in the session list of a real deployment is whatever `NUM_PROXIES` yields; wrong values mislead | |
| I-1 | Info | No index supports the incident-list order (128 ms at 300k rows for a team member); retention scans sequentially; `/users/` and `/overrides/` are unpaginated; `set_mode` holds the service row while resolving maintenance alerts (2.4 s at 172,800 alerts) | |
| I-2 | Info | `scripts/mutate.py` is not run in CI (about 10 minutes); the frontend has 31% line coverage and no threshold; two frontend routes (`RequireAuth`, `SecurityPage`) have none | |
| I-3 | Info | `SKIP LOCKED` in the escalation claim is not part of the no-double-page mechanism (the mutation harness's one documented survivor): without it a held row stalls a sweep for up to the lock timeout instead of deferring to the next sweep. INVARIANTS I4 and decision 3 still list it among the mechanisms | |
| I-4 | Info | Action links are bearer tokens that bypass the admin MFA-enrolment gate, and webhook payloads carry them: anyone who can read the target channel can act as the paged person | Documented design |
| I-5 | Info | nginx forwards a client-supplied `X-Forwarded-Proto` when it is the edge, does not set `server_tokens off`, and lacks `interest-cohort` in `Permissions-Policy` | |

## Mutation testing

The harness (`scripts/mutate.py`) applies one small, realistic breakage to a critical line and requires the named tests to fail. It started this audit at 74 mutations (73 caught, one documented equivalent survivor). The audit added its own mutations; every one that survived the whole suite is now pinned. **Final full run of `python3 scripts/mutate.py` on this branch: 94 mutations, 93 caught, 1 survived (`skip-locked`, the documented equivalent), 0 invalid.** Two earlier full runs aborted because two of my own edits (`no_key=True`, `DEMO_ACCOUNT_GUARD`) had changed the lines three mutations match on; the harness refuses a pattern that no longer matches exactly once, which is how I found them.

| Category | Mutation (file) | Breakage | Result | Caught by |
|---|---|---|---|---|
| Scoping | `scope-services`, `-policies`, `-oncalls`, `-schedules`, `-incidents`, `-analytics`, `-teams`, `-users`, `-notifications` (each list view) | queryset not restricted to the caller's teams | caught | `test_tenant_matrix.py` (one case per route) |
| Scoping | `scope-overrides` (`schedules/views.py`) | overrides readable across teams | caught | tenant matrix |
| Scoping | `scope-timeseries`, `scope-sessions-list` | count-only chart and session list unscoped | caught (new) | `test_audit_gaps.py` |
| Claim lock | `deliver-claim-lock` (`notifications/actions.py`) | no row lock on the claim | caught (new test) | `test_claiming_a_row_waits_for_whoever_holds_its_lock` |
| Claim lock | `skip-locked` (`escalations/engine.py`) | blocking `FOR UPDATE` instead of `SKIP LOCKED` | **survives, documented equivalent** (no double or lost page in 8-thread and 12×3-round probes; differs only in latency) | none by design |
| Dedup | `dedup-index` (`incidents/migrations/0001`) | partial unique index removed | caught | `test_dedup_constraint.py` |
| Dedup | `ingest-advisory-lock`, `ingest-row-lock` | alert race | caught | ingest concurrency tests |
| Idempotency key | `idempotency-key` (`notifications/actions.py`) | page key format changed | caught | `test_delivery.py::test_idempotency_key_format` |
| Idempotency key | `notification-key-unique` (migration) | `UNIQUE` dropped on the page key | caught (new) | `test_audit_gaps.py` |
| Idempotency header | `idempotency-replay`, `idempotency-caller-scope`, `secret-response-tombstone` | replay, scope, secrets stored | caught | `test_api_quality.py` |
| Idempotency header | `idem-in-flight`, `idem-events-scope` | in-flight lock, per-key scope | caught (new) | `test_audit_gaps.py` |
| on_commit | `on-commit` (`core/dispatch.py`), `deliver-direct-enqueue` | enqueue before commit | caught | `test_dispatch_order.py` |
| Inactive filter | `inactive-users` (`escalations/engine.py`), `rules-enabled`, `maintenance-guard`, `resolved-guard` | wrong people paged | caught | engine, rules and delivery tests |
| Signed link | `link-signature`, `link-expiry`, `link-single-use`, `link-actor-check` | forged or replayed one-tap links | caught | `test_action_links.py` (every single-bit flip) |
| Webhook signature | `twilio-signature`, `twilio-sig-params` | forged receipts | caught | `test_twilio_webhooks.py` |
| MFA | `mfa-login-gate`, `totp-replay`, `backup-code-single-use`, `mfa-attempt-limit`, `mfa-enrolment-gate` | second factor skipped or replayed | caught | `test_mfa.py`, `test_totp.py` |
| MFA | `mfa-account-lockout`, `throttle-skips-signed-in` | per-account cap, signed-in bypass | caught (new) | `test_sign_in_limits.py` |
| Headers and cookies | `hsts-default-off`, `cookie-secure-off`, `cookie-httponly-off`, `cookie-samesite-none` | weaker flags | caught (new) | `test_audit_gaps.py` |
| Integration key | `key-grace-expiry`, `integration-key-no-store` | rotated key works forever, key stored | caught | catalog tests |
| Integration key | `key-prefix-compare` | key matched on its first 8 characters | caught (new) | `test_audit_gaps.py` |
| Demo and deploy | `demo-session-lock`, `demo-hides-addresses`, `prod-requires-num-proxies`, `prod-docs-off`, `swagger-unpinned`, `broker-socket-timeout`, `demo-cache-cap`, `backup-prune-empty-dir` | this audit's fixes | caught (new) | their own tests |

Mutations the audit tried that the harness did not already have: 27 by the mutation reviewer; 13 survived and were fixed above, and the remainder were caught on first run. Three that the reviewer judged weak are recorded as I-2 and L-10.

## Claim ledger

122 checkable claims across the README, INVARIANTS, ARCHITECTURE, DEPLOY, RUNBOOK, OBSERVABILITY, DATA_SAFETY, CHANNELS, SECURITY_MODEL, TENANCY, API, SECURITY and CONTRIBUTING were checked against code, tests or a command. **102 true, 12 partly true, 3 false, 5 not verifiable here.** All 82 test references in INVARIANTS.md exist and pass, the invariant tests named were read to confirm they exercise the claim, and all 75 relative links in the docs resolve. The 102 true rows are not repeated; every other row is:

| Claim | Verdict | Evidence | Status |
|---|---|---|---|
| README: "the one survivor, `skip-locked`" | false | the harness had two survivors; `deliver-claim-lock` had no test | fixed (new test); one survivor again |
| DATA_SAFETY: drill covers "24 tables, 400 incidents, 88 indexes, 92 constraints" | false | the drill measured 31, 407, 114, 115 | fixed (counts removed) |
| DATA_SAFETY: migrations "pass 11/11" | false | 17 migrations, one warning | fixed |
| I4: each row delivered "at most once" | partly | at-least-once across failures (M-9) | fixed (reworded) |
| I4 and README: `SKIP LOCKED` as part of no-double-page | partly | latency optimisation only (I-3) | README softened; INVARIANTS and decision 3 still list it |
| I5: stuck rows re-dispatched "after two minutes" | partly | `STUCK_AFTER` is 90 s | fixed |
| I5: none stays pending forever | partly | a dead last attempt did (F-8) | fixed |
| ARCHITECTURE: notification statuses | partly | `cancelled` missing | fixed |
| ARCHITECTURE: "a broker failure is logged and moved on" | partly | only for a refused connection; a hung broker blocked (F-9) | fixed |
| DECISIONS 18: HSTS defaults to 0; "23 mutations" | partly | the default is a year; the count was stale | fixed |
| DATA_SAFETY: heartbeat and upload only on success; restore refuses the live database | partly | skipped on non-Sundays (F-1); string comparison only (L-9) | F-1 fixed; L-9 open |
| README: CI runs `make doctor` on every push in "about 8 minutes" | partly | the job took about 6 minutes | left |
| RUNBOOK: `/readyz` ok, degraded and 503 | partly | ok and 503 seen locally; degraded only in CI logs | left |
| SECURITY_MODEL: Django pages use a per-request nonce CSP | partly | an API response carries none (it is JSON); an HTML page was not probed | left |
| README load figures (77 req/s, p95 532 ms); `make up`, `make doctor`, `make chaos-redis` | not verifiable | need Docker | see NOT VERIFIED |
| I11: regressions "fail against the pre-fix resolver" | not verifiable | no pre-fix tree | |
| SECURITY_MODEL: password policy | not verifiable | the named test exists and passes | |

## NOT VERIFIED

- **Anything that needs Docker:** `make up`, `make doctor`, `make doctor-demo` on the real compose files, image builds, Trivy image scans and SBOMs, `make chaos-redis`, `scripts/deploy.sh`, the Caddy overlay, container health checks, and k6 as run by CI. Their evidence is the CI run on `main`, whose job conclusions and the `docker-smoke` (42 checks), `demo-doctor` (38) and E2E (2) lines were read; the k6, Trivy-image and promtool lines were not.
- **The public demo.** It is not deployed. A Render service exists but fails to boot until the owner sets `DATABASE_URL`. Everything about it was tested only against a locally started demo.
- **A real third-party service:** Twilio, Slack, a mail provider or a heartbeat monitor. Tests use fakes; the heartbeat drills used a local stand-in.
- **Real DNS in the SSRF tests** (the resolver was simulated), CSP and HSTS enforcement in a browser, and login-timing enumeration.
- **The live second-factor brute-force path** (finding F-3): the reviewer's attempt was stopped by a safety classifier; the finding rests on reading the code, and the fix is covered by tests.
- **The correct `NUM_PROXIES` for the full-stack Render blueprint** (set to 3 from the topology).
- **PostgreSQL 17** (every local run used 16; CI uses 17).
- **A full gunicorn brown-out under a hung broker** (only the per-call hang was shown), the real frequency of the deadlock and stuck-page defects, and real Celery redelivery past the visibility timeout.
- **Capacity.** The load run shared four cores with other jobs.
- **Third-party review.** None.

## Residual risks

What a reader deciding whether to run this should still weigh:

1. **A page can arrive more than once** (M-9) and **an email outage of 20 seconds can lose the email page** (M-12). Both are bounded and the in-app page and escalation remain.
2. **An alert at the instant a maintenance window ends can be swallowed** (M-10).
3. **Detection is slower than the docs imply** and has a blind spot when Redis and Beat fail together (M-13, M-14).
4. **The full-stack Render blueprint's `NUM_PROXIES` is unmeasured.** A wrong value is silent.
5. **The demo's shared logins** are public by design; the guards limit what a visitor can do to others, not what they can do to the demo's data (it is reseeded daily).
6. **No third party has reviewed this**, and the application has never carried real traffic.

## How to reproduce

```bash
git clone https://github.com/santheesh73/PagerDuty.git && cd PagerDuty
cd backend && uv sync --frozen
uv run ruff check . && uv run ruff format --check . && uv run mypy .
uv run pytest --cov --cov-report=xml --junitxml=pytest.xml --cov-fail-under=85
python3 ../scripts/readme_numbers.py --check --junit pytest.xml --coverage coverage.xml
cd .. && python3 scripts/mutate.py                 # about 10 minutes; --list and --only exist
make audit                                         # pip-audit, npm audit, Trivy (needs uv, npm, curl)
make doctor && make doctor-demo                    # need Docker
```

Run the test suite on **different days of the week**: the bug that most embarrassed this audit only appeared on non-Sundays. The security and operations probes were throwaway scripts against real PostgreSQL and are not committed; the behaviours they exercised are now covered by committed tests (`apps/security/tests/test_sign_in_limits.py`, `apps/core/tests/test_audit_gaps.py`, `test_prod_settings.py`, `test_broker_settings.py`, `apps/incidents/tests/test_ack_vs_settle.py`, and the additions to `test_delivery_claim.py`, `test_backup_scripts.py`, `test_demo_mode.py`, `test_tenant_matrix.py`).
