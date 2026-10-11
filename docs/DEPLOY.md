# Deploying Pulse

There are two ways to deploy Pulse:

| | What runs | Cost | For |
|---|---|---|---|
| [**Free demo**](#1-the-free-demo) | One container ([`deploy/demo/Dockerfile`](../deploy/demo/Dockerfile)) and a free Postgres | $0 | A public demo |
| [**Real deployment**](#2-a-real-deployment-on-one-docker-host) | The full stack ([`docker-compose.prod.yml`](../docker-compose.prod.yml)) behind Caddy TLS, with backups, deploys and rollback | One small VM (2 GB RAM) | Running it for real |

Both use the same code. The demo trades the background workers for an HTTP "tick". The guarantees still come from Postgres, so a missing worker delays work but never loses it.

## 1. The free demo

### What demo mode changes

`DEMO_MODE=1` runs Pulse with no Redis and no Celery:

- **Work due now runs in-process, right after commit.** An alert's first pages are sent before the Events API call returns. The code path is the same one a worker would run, with the same claim/send/settle and unique keys, so nobody is paged twice (I4).
- **Work due later is driven by `POST /internal/tick/`.** This covers escalation timers, the later steps of personal notification rules, retries after a failed send, and the end of maintenance and debug windows. Each tick does what Beat would have done since the last one. Ticks are idempotent and safe to overlap. Timers are already columns in Postgres and pages are already rows, so the gap between ticks is how late an escalation can be. Nothing is lost.
- **The cache lives in Postgres** (`createcachetable`). Throttles, the sign-in lockout, idempotency keys and the heartbeat are shared by every gunicorn worker. Counters are correct on this backend too (`core/tests/test_counters.py`).
- **Django serves the SPA itself**, with the SPA's own Content-Security-Policy, so one container is the whole app.
- **The public demo is protected from its visitors.** Its logins are printed on the sign-in page, so the shared `@demo.local` accounts can't change their password or two-factor settings (`core/demo.py`). `DEMO_RESET_HOURS=24` reseeds everything daily, and the image turns off `REQUIRE_MFA_FOR_ADMINS` so the shared admin can sign in.

Ticks come from three places. Any one of them is enough:

1. **The demo ticks itself** (`DEMO_SELF_TICK_SECONDS=30`): after a response has been sent, at most every 30 s. Timers advance whenever anyone is using it, with nothing configured.
2. **[`.github/workflows/demo-tick.yml`](../.github/workflows/demo-tick.yml)** calls the tick every 5 minutes once the repository has two secrets: `PULSE_TICK_URL` (`https://<host>/internal/tick/`) and `PULSE_TICK_SECRET`. It also keeps a free instance from sleeping.
3. **Any cron** that can send `POST` with an `X-Tick-Secret` header, such as cron-job.org.

The tick answers 404 unless `DEMO_MODE` is on and `TICK_SECRET` is set. It compares the secret in constant time and allows 12 calls a minute per address, counted before the secret is checked (`core/tests/test_demo_mode.py`).

**Limits of the free demo, plainly:**

- A free instance sleeps after about 15 minutes without traffic, and the first request then takes up to a minute.
- Escalations fire on the next tick: within 30 s while someone is using the demo, within about 5 minutes with the scheduled tick, and on the next visit otherwise.
- Pages are emailed to the service's log (there is no SMTP server), and SMS and voice are off. The in-app inbox works.
- Render's free Postgres expires 30 days after creation, and a workspace can have only one. Recreate it, or point `DATABASE_URL` at a free Neon database. A free web service gets 750 instance-hours a month, enough to stay awake all month.
- The workers, Beat and Redis path is not what the demo runs. `make doctor` proves that path in CI; `make doctor-demo` proves this one.

### On Render

[`render.yaml`](../render.yaml) is a Blueprint for exactly this: one free web service and one free Postgres.

1. In Render: **New → Blueprint**, then pick this repository. Render builds `deploy/demo/Dockerfile` and generates `SECRET_KEY` and `TICK_SECRET`.
2. If the name `pulse-demo` is taken, rename the service and update `CSRF_TRUSTED_ORIGINS` and `FRONTEND_URL` to match.
3. Optional, for the 5-minute tick: copy the service's `TICK_SECRET` into the repository secret `PULSE_TICK_SECRET`, and set `PULSE_TICK_URL` to `https://<service>.onrender.com/internal/tick/`.
4. Check it: `EXPECT_DEMO=1 SMOKE_EMAIL=responder@demo.local SMOKE_PASSWORD=demo1234 ./scripts/smoke.sh https://<service>.onrender.com`.

### Anywhere else (Koyeb, Fly.io, a VM) with any Postgres (Neon, Supabase)

Build `deploy/demo/Dockerfile` with the repository root as context, then set:

| Variable | Value |
|---|---|
| `DATABASE_URL` | Postgres 16 or newer, e.g. a free Neon database (`?sslmode=require`) |
| `SECRET_KEY`, `TICK_SECRET` | `openssl rand -hex 32` and `openssl rand -hex 16` |
| `ALLOWED_HOSTS` | Your public hostname |
| `CSRF_TRUSTED_ORIGINS`, `FRONTEND_URL` | `https://<hostname>` |
| `NUM_PROXIES` | How many proxies append to `X-Forwarded-For` in front of the container (usually 1) |
| `PORT` | The port the platform routes to (default 8000) |

Health check: `GET /healthz`. The container migrates, seeds and starts gunicorn on its own.

### Locally

```bash
export SECRET_KEY=$(openssl rand -hex 32) TICK_SECRET=$(openssl rand -hex 16)
docker compose -f docker-compose.demo.yml up --build -d     # http://localhost:8080
make doctor-demo     # boots it from scratch and proves alert → page → escalate → ack → resolve
```

## 2. A real deployment on one Docker host

The full stack: API, a worker for escalations only, a worker for notifications, Beat, Redis, Postgres, nginx and scheduled backups. [`deploy/compose.production.yml`](../deploy/compose.production.yml) adds Caddy for TLS, real hostnames and secrets, and release-tagged images, and drops the local-only pieces.

You need a VM with 2 GB of RAM and Docker Compose 2.24 or newer, a DNS record pointing at it, ports 80 and 443 open, and an SMTP server for pages.

```bash
git clone https://github.com/santheesh73/PagerDuty.git pulse && cd pulse
cp deploy/.env.production.example .env.production   # fill in DOMAIN, secrets, SMTP
./scripts/deploy.sh                                  # deploys origin/main
```

`scripts/deploy.sh [ref]`:

1. checks out the release and builds images tagged with its git SHA;
2. runs `migrate_safely` once, before any new process serves traffic;
3. starts the release and waits for every health check;
4. runs `scripts/smoke.sh https://$DOMAIN`.

If the smoke test fails, it switches straight back to the previous release. If it passes, it records the release as live and the old one as the rollback target.

- `./scripts/deploy.sh --rollback` restarts the previous release on images already on the host: no rebuild and no registry.
- `./scripts/deploy.sh --status` shows the live release and the rollback target.

**Migrations are never reversed.** That is safe because every migration is expand-only: new columns have database defaults, indexes are built concurrently, and nothing is dropped in the same release that stops using it. `make lint-migrations` enforces this in CI, so the previous release always works against the newer schema ([DATA_SAFETY.md](DATA_SAFETY.md)). A change that cannot be expand-only, such as phase 4's hashed integration keys, says so in [DECISIONS.md](DECISIONS.md) and deploys with a stop-then-start.

**Backups** run in the `backup` service, nightly by default. They keep 7 daily and 4 weekly backups and, with `BACKUP_S3_*` set, copy each one off the host. `make backup-drill` proves a restore works ([DATA_SAFETY.md](DATA_SAFETY.md)). Set `BACKUP_HEARTBEAT_URL` so a backup that stops running alerts you.

**Monitoring:**

- `HEARTBEAT_URL`, a dead-man's switch that alerts when Pulse stops paging;
- `SENTRY_DSN`;
- `/metrics` with `METRICS_TOKEN`, plus the Prometheus and Grafana overlay ([OBSERVABILITY.md](OBSERVABILITY.md)).

**Security defaults in this overlay:**

- HTTPS only, secure `__Host-` cookies and HSTS for one year;
- `REQUIRE_MFA_FOR_ADMINS=1`;
- no demo data, and no demo logins on the sign-in page;
- `NUM_PROXIES=2` (Caddy, then nginx), so throttles see the real client address.

Create the first staff account with `docker compose … exec api python manage.py createsuperuser`; it must set up MFA at first sign-in.

## Post-deploy smoke test

`scripts/smoke.sh <url>` checks, from the outside:

- liveness and readiness;
- the SPA, its CSP and nosniff header;
- HSTS and the HTTP→HTTPS redirect;
- the API's error envelope for anonymous callers and unknown paths;
- the one-tap action links;
- the CSRF cookie.

Optionally it also signs in (`SMOKE_EMAIL`/`SMOKE_PASSWORD`) and calls the tick (`TICK_SECRET`). It needs only curl, and exits non-zero on any failure. `deploy.sh` runs it on every deploy.

## What has and hasn't been exercised

- **Proven in CI on every push:**
  - the demo image boots with no Redis or Celery and runs the whole alert flow through ticks (`demo-doctor`);
  - the full stack boots and survives its failure drills (`docker-smoke`);
  - every image builds, is scanned, and gets an SBOM;
  - the production overlay resolves, Caddy accepts its config, and the scripts pass shellcheck.
- **Not exercised end to end:** `deploy.sh` on a real host, against a real domain and certificate. It is built from the pieces above, but a first real deployment should watch it closely.
