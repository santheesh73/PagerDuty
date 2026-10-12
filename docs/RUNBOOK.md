# Runbook

Operating Pulse: what runs where, how to tell it is healthy, and what to do when it is not.
Everything below was exercised against a real Docker stack by `make doctor` (see
[the failure drills](#what-make-doctor-proves)).

## Stacks

| | Dev (`make up`) | Production-like (`docker-compose.prod.yml`, `make doctor`) |
|---|---|---|
| Compose file | `docker-compose.yml` | `docker-compose.prod.yml` |
| App URL | <http://localhost:5173> (Vite, hot reload) | <http://localhost:8080> (nginx + built bundle) |
| API | <http://localhost:8000> | via nginx at `/api` (not published directly) |
| Mail inbox (Mailpit) | <http://localhost:8025> | <http://localhost:8025> |
| Source | bind-mounted (`./backend`, `./frontend`) | baked into images, runs as non-root `pulse` |
| Settings | `config.settings.dev` | `config.settings.prod` (refuses to start without `SECRET_KEY`, `ALLOWED_HOSTS`, `DATABASE_URL`) |
| Demo data | `SEED_DEMO=1` by default | off by default; `SEED_DEMO=1 SHOW_DEMO_CREDENTIALS=true` for a demo |

Host ports used: `5173`, `8000`, `8025` (dev) or `8080`, `8025` (prod-like). Postgres, Redis and SMTP are
internal to the Compose network. Stop one stack before starting the other (both want `8025`).

## Services

| Service | Role | Healthcheck |
|---|---|---|
| `db` | PostgreSQL 17, the only source of truth | `pg_isready` |
| `redis` | Broker + throttle cache, persistence **off** on purpose (wiping it loses no incident) | `redis-cli ping` |
| `mailpit` | SMTP sink with an inbox UI (dev, smoke tests) | `mailpit readyz` |
| `backend` / `api` | Django + DRF under gunicorn; runs `migrate` (and the optional seed) on every start | `GET /healthz` (liveness) |
| `worker-escalations` | Celery, consumes only the `escalations` queue | `celery inspect ping` (a broker round trip to this worker) |
| `worker` | Celery, `notifications` + `default` queues | same |
| `beat` | Celery Beat: due-escalation sweep 30 s, mode expiry 60 s, stuck-notification sweep 60 s | exactly one beat process is running |
| `frontend` / `web` | Vite dev server / nginx serving the SPA and proxying `/api`, `/admin`, `/healthz`, `/readyz` | HTTP 200 on `/` |

Start order is enforced with `depends_on: condition: service_healthy`: `db`, `redis` and `mailpit`, then the
API (which migrates), then workers, beat and the frontend. Migrations run once, in the API's entrypoint;
workers and beat start only after the API is healthy, so there is no migration race.

## Health endpoints

| Endpoint | Meaning | Status |
|---|---|---|
| `GET /healthz` | The process is up; touches nothing. Used by container healthchecks and platforms, so a store blip never restarts a healthy web process. | always 200 |
| `GET /readyz` | Can this instance serve traffic? Checks Postgres and Redis. | `200 {"status":"ok"}`; `200 {"status":"degraded"}` if only Redis is down (the API still ingests and commits; the sweepers catch up); `503 {"status":"unavailable"}` if Postgres is down |

## Environment variables

Copy `.env.example` to `.env` for local use (it is git-ignored). Compose passes the rest.

| Variable | Default | Notes |
|---|---|---|
| `SECRET_KEY` | dev placeholder | **Required** in prod. `openssl rand -hex 32` |
| `DJANGO_SETTINGS_MODULE` | `config.settings.dev` | the prod image sets `config.settings.prod` |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS`, `FRONTEND_URL` | see `.env.example` | prod compose sets them for `localhost:8080` |
| `DATABASE_URL`, `REDIS_URL` | local Postgres/Redis | Compose overrides with service hostnames |
| `SEED_DEMO` | `1` dev, `0` prod | demo teams, users, services and history; idempotent |
| `SHOW_DEMO_CREDENTIALS` | `false` | prod web build arg: print the demo logins on the sign-in page |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_TIMEOUT`, `DEFAULT_FROM_EMAIL` | unset → console | setting `EMAIL_HOST` selects real SMTP; `EMAIL_TIMEOUT` defaults to 10 s. An explicit `EMAIL_BACKEND` always wins over `EMAIL_HOST` |
| `API_DOCS` | on in dev, off in production settings | Swagger UI at `/api/docs/` (a CDN script on the session origin, so production serves it only when `API_DOCS=1`) |
| `DEMO_ACCOUNT_GUARD` | follows `DEMO_MODE` | the shared `@demo.local` logins can't change credentials or end sessions, and session/audit lists hide visitors' addresses; set alone for a full stack that seeds the demo |
| `MFA_LOCKOUT_FAILURES`, `MFA_LOCKOUT_SECONDS` | 10, 900 | wrong two-factor codes per account before the code step locks, across password steps |
| `NUM_PROXIES` | unset (dev), required in production, `1` (prod compose) | reverse proxies you trust to append to `X-Forwarded-For`; used for throttling. Unset trusts the whole header (spoofable), so production settings refuse to start without it |
| `THROTTLE_LOGIN`, `THROTTLE_EVENTS` | `10/min`, `120/min` (per key) | rate limits |
| `GUNICORN_WORKERS`, `CELERY_CONCURRENCY`, `CELERY_QUEUES` | `3`, `4`, all three queues | the compose files give `worker-escalations` `CELERY_QUEUES=escalations` |
| `METRICS_TOKEN`, `HEARTBEAT_URL`, `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_RELEASE`/`GIT_SHA` | unset (off) | observability, see [OBSERVABILITY.md](OBSERVABILITY.md): `/metrics` is a 404 without a token |
| `BACKUP_*`, `RETENTION_DAYS`, `DB_STATEMENT_TIMEOUT_MS`, `DB_LOCK_TIMEOUT_MS`, `DB_IDLE_IN_TX_TIMEOUT_MS`, `DB_CONN_MAX_AGE` | see DATA_SAFETY.md | backups (the compose `backup` service), retention (0 = keep everything), database session limits |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `PUBLIC_BASE_URL`, `ACTION_LINK_TTL_HOURS` | unset (SMS/voice off), FRONTEND_URL, 12 | channels, see [CHANNELS.md](CHANNELS.md) |
| `REQUIRE_MFA_FOR_ADMINS`, `SESSION_HOURS`, `LOGIN_LOCKOUT_FAILURES`, `LOGIN_LOCKOUT_SECONDS`, `INTEGRATION_KEY_GRACE_HOURS`, `CSP_MODE`, `CSP_CONNECT_EXTRA` | on in prod settings (off in the local compose stacks), 12, 10, 900, 24, enforce, - | see [SECURITY_MODEL.md](SECURITY_MODEL.md) |
| `DEMO_MODE`, `TICK_SECRET`, `DEMO_SELF_TICK_SECONDS`, `DEMO_RESET_HOURS`, `SPA_DIR`, `PORT` | off, unset, 0, 0, unset, 8000 | the one-container demo, see [DEPLOY.md](DEPLOY.md): no Redis or Celery, timers driven by `POST /internal/tick/` (404 unless both of the first two are set), Django serving the SPA from `SPA_DIR`. `PORT` is the API's listen port in every mode |
| `SECURE_COOKIES`, `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS` | `1`, `1`, one year in prod settings | the prod compose sets the first two to `0` for plain-HTTP `localhost`; **set them for real deployments** (HSTS is sticky, see DECISIONS #18) |

## Everyday commands

```bash
make up            # build + start + wait until healthy        make down      # stop, keep data
make logs          # tail every service                         make ps        # status
make migrate       # apply migrations (also runs on API start)  make seed      # demo data (idempotent)
make db-backup     # backups/pulse-<time>.dump                  make db-restore FILE=backups/pulse-<time>.dump
make doctor        # prove the whole stack, ~8 minutes
make doctor-demo   # the same proof for the one-container demo (no Redis, no Celery)
make chaos-redis   # wipe Redis mid-incident and assert nothing is lost
make readme-numbers  # re-measure the README's test counts, coverage and badge (CI fails if they drift)
```

Re-record the README's GIF and the social preview from the real app after a UI change: start a seeded stack on
<http://localhost:8080> (`docker compose -f docker-compose.demo.yml up --build -d`, or the prod-like
stack with `SEED_DEMO=1`), then `TICK_SECRET=<its secret> ./scripts/record_demo.sh` (the secret is
only needed for the demo stack, which has no Beat). It needs Node, ffmpeg and a Playwright Chromium
(`cd e2e && npm ci && npx playwright install chromium`); one take is about two minutes, most of it
waiting for the one-minute escalation.

Read logs for one service: `docker compose logs -f --tail=200 worker-escalations`. Logs are JSON with a
`request_id` that also appears in the Celery task logs the request caused.

Reset everything (**destroys data**): `docker compose down -v`. Reset only the demo data: `make reseed`.

## Backup and restore

The prod-like stack runs a `backup` service (verified `pg_dump`, rotation, optional S3 upload) and
`make backup-drill` proves a restore end to end: see [DATA_SAFETY.md](DATA_SAFETY.md) for RPO/RTO, the
restore procedure and migration rules. The quick manual form:

`make db-backup` runs `pg_dump -Fc` inside the `db` container. `make db-restore FILE=...` pipes a dump into
`pg_restore --clean --if-exists`. Verified: a dump restored into a scratch database had identical row counts
for incidents, alerts, notifications and users, and the partial unique index `uniq_open_incident_per_dedup_key`
came back. Redis needs no backup: it is a disposable broker.

## What `make doctor` proves

`scripts/doctor.sh` boots the prod-like stack from scratch (fresh volumes), runs `scripts/doctor.py`, saves
the logs to `doctor-logs.txt` on failure and tears down (`KEEP=1` leaves it running, `SKIP_DRILLS=1` skips the
drills). Checks, each reported PASS/FAIL:

- liveness, readiness, the SPA and its security headers, the API through nginx
- sign-in (and a refused wrong password), creating a service through the API
- a multi-line alert becomes one incident with a one-line title; a duplicate attaches to it
- the page reaches the inbox exactly once; an unanswered page escalates on its own to level 2
- forged `X-Forwarded-For` prefixes do not reset the login throttle
- **Redis down**: `/readyz` says `degraded`, alerts are still accepted, and after Redis returns every page
  arrives exactly once and the incident still escalates
- **Workers restarted mid-escalation**: nothing is lost or duplicated
- **Database down**: `/readyz` is 503, `/healthz` stays 200, alerts fail cleanly (5xx), and the stack recovers
  with no manual step
- **API crashes**: SIGKILLed gunicorn workers are respawned; the API process exiting by itself is restarted
  by the restart policy and migrations re-run harmlessly

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| Pages never appear in Mailpit | `EMAIL_BACKEND` pinned to `console` in an old `.env` | delete that line (compose now forces SMTP to Mailpit in dev); with a real host set `EMAIL_HOST` and leave `EMAIL_BACKEND` unset |
| Email page `failed` after 5 attempts | a header problem (multi-line title) or SMTP unreachable | titles are now collapsed to one line; check `last_error` on the notification and the worker log; check `EMAIL_HOST`/`EMAIL_TIMEOUT` |
| Login returns 429 for everyone | `NUM_PROXIES` too high/low behind your own proxy chain, so every client shares one address | set it to the number of trusted hops; with nginx as the only proxy, `1` |
| `docker compose kill api` and it stays down | a kill is a manual stop and restart policies respect it | `docker compose up -d api`. A real crash is restarted automatically |
| First page late after a Redis outage | its delivery message was lost; the 60 s stuck-notification sweep re-drives rows older than 90 s | wait up to ~2.5 minutes; check `beat` is healthy |
| `/readyz` says `degraded` | Redis unreachable (alerts still work) | restore Redis; the sweepers catch up on their own |
| `/readyz` is 503 | Postgres unreachable | restore the database; the API reconnects without a restart |
| Port already allocated on `8025`/`8080`/`5173`/`8000` | the other stack or another program is using it | `make down` the other stack |
| Two `beat` processes | a second Compose project or a scaled service | run exactly one; the healthcheck fails unless there is exactly one |
| `make test` / `make check` were several times slower than CI | `.env` exports `DJANGO_SETTINGS_MODULE=config.settings.dev`, and an environment variable beats `pytest.ini` | fixed: pytest now pins `--ds=config.settings.test`, guarded by `test_the_suite_runs_on_test_settings_whatever_the_environment_says` |

## Design notes an operator should know

- **Escalation timers live in Postgres.** Wiping Redis loses no incident; the 30 s sweeper escalates anything
  due. `make chaos-redis` asserts this.
- **At-least-once delivery, sent-at-most-once per attempt.** `deliver` claims a notification (counting the
  attempt), sends with no transaction open, then records the result. A worker that dies mid-send leaves a
  claim that expires after 60 s; the next delivery retries and the dead try counts toward the 5-attempt cap.
- **`-Q` order is not a queue priority.** Paging is isolated by `worker-escalations`, which consumes nothing
  else. On a single-worker host all three queues share one process.
- **Redis broker visibility timeout** is left at Redis' default (1 h). ETA tasks further out than that may be
  redelivered; this is harmless because `escalate` re-checks under a row lock and the database is the timer.
