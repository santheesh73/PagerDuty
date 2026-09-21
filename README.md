# Incident Management Platform

A deterministic, production-grade incident management platform providing automated alert ingestion, deduplication, on-call scheduling, tiered escalation policies, notification delivery, and incident lifecycle tracking.

---

## 1. Project Overview

The Incident Management Platform coordinates emergency response workflows during production incidents. It handles alert triage, dedupes recurring alerts against active incidents, identifies service escalation policies and on-call responders, triggers automated notifications, and manages incident escalation and resolution states with auditable event histories.

---

## 2. Architecture

```
React 18 + TypeScript + Vite
        │
        │ REST / JSON
        ▼
Django 5.x + Django REST Framework
        │
        ├──────────────────────► PostgreSQL 15+
        │
        ▼
Redis 7.x
        │
        ▼
Celery 5.x workers
        │
        └──────────────────────► PostgreSQL
```

### Component Responsibilities:
- **Django**: Owns the domain model, business rules, REST APIs, payload validation, and workflow orchestration.
- **PostgreSQL**: Single source of truth storing all users, services, alerts, incidents, schedules, escalation policies, notifications, and event history.
- **Redis**: In-memory broker for Celery task queues.
- **Celery**: Asynchronous worker execution for escalation timers, retries, notification dispatch, and scheduled checks.
- **React**: Thin REST client statefully rendered via TanStack Query; contains no server domain or business logic.

---

## 3. Technology Stack

- **Backend**: Python 3.11, Django 5.1+, Django REST Framework 3.15+, Celery 5.4+, Psycopg 3.3+, Ruff
- **Database & Broker**: PostgreSQL 16+, Redis 7+
- **Frontend**: React 18, TypeScript 5, Vite 5, Tailwind CSS 3, TanStack React Query 5, Vitest
- **Containerization**: Docker, Docker Compose

---

## 4. Repository Structure

```
incident-platform/
├── README.md                 # System overview and developer instructions
├── docker-compose.yml        # Development stack definition (Postgres, Redis, Backend, Celery, Frontend)
├── .env.example              # Environment variable baseline template
├── .gitignore                # Git exclusions
├── skills/                   # Repository skills and workflows
├── transcripts/              # Authentic session records and logs
├── e2e/                      # End-to-End test suite foundation
│
├── backend/
│   ├── manage.py             # Django administrative entrypoint
│   ├── pyproject.toml        # Backend configuration and dependency definitions
│   ├── requirements.txt      # Production dependencies
│   ├── requirements-dev.txt  # Development and test dependencies
│   ├── Dockerfile            # Backend container definition
│   ├── pytest.ini            # Pytest configuration
│   ├── config/               # Project configuration & settings
│   │   ├── __init__.py       # Celery app export
│   │   ├── celery.py         # Celery configuration and smoke tasks
│   │   ├── urls.py           # Root routing & /api/health/ endpoint
│   │   ├── wsgi.py           # WSGI entrypoint
│   │   ├── asgi.py           # ASGI entrypoint
│   │   └── settings/         # Split settings modules
│   │       ├── __init__.py
│   │       ├── base.py       # Shared settings
│   │       ├── dev.py        # Development settings
│   │       └── prod.py       # Production hardened settings
│   ├── apps/                 # Domain applications
│   │   ├── users/            # Users, Teams, TeamMembership
│   │   ├── services/         # Services
│   │   ├── alerts/           # Alerts & triage pipeline
│   │   ├── incidents/        # Incidents & state machines
│   │   ├── scheduling/       # On-call schedules & rotations
│   │   ├── escalation/       # Escalation policies & levels
│   │   ├── notifications/    # Notifications & dispatch
│   │   └── analytics/        # MTTA / MTTR metrics
│   ├── fixtures/             # Data fixtures
│   └── tests/                # Infrastructure & integration test suite
│
└── frontend/
    ├── package.json          # Node dependencies & scripts
    ├── vite.config.ts        # Vite configuration
    ├── vitest.config.ts      # Vitest test runner configuration
    ├── tailwind.config.js    # Tailwind CSS configuration
    ├── tsconfig.json         # TypeScript configuration
    ├── Dockerfile            # Frontend container definition
    └── src/
        ├── main.tsx          # Application entrypoint
        ├── App.tsx           # QueryClientProvider and root component
        ├── api/              # Typed API client & endpoints
        ├── hooks/            # TanStack Query custom hooks
        ├── types/            # TypeScript type declarations
        ├── components/       # Shared UI components
        └── pages/            # View components & status dashboard
```

---

## 5. Environment Variables

Copy the template to initialize your local environment:

```bash
cp .env.example .env
```

| Variable | Description | Default / Example |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | Active Django settings module | `config.settings.dev` |
| `DJANGO_SECRET_KEY` | Application cryptographic secret | *Random secret string* |
| `DJANGO_DEBUG` | Debug mode toggle | `True` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed hostnames | `localhost,127.0.0.1,backend,web` |
| `POSTGRES_DB` | PostgreSQL database name | `incident_platform` |
| `POSTGRES_USER` | PostgreSQL user | `postgres` |
| `POSTGRES_PASSWORD` | PostgreSQL password | `postgres` |
| `POSTGRES_HOST` | PostgreSQL host | `localhost` or `postgres` |
| `POSTGRES_PORT` | PostgreSQL port | `5432` |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `CELERY_BROKER_URL` | Celery broker URL | `redis://localhost:6379/0` |
| `CELERY_RESULT_BACKEND` | Celery result backend URL | `redis://localhost:6379/1` |
| `VITE_API_BASE_URL` | Frontend REST API base URL | `http://localhost:8000/api` |

---

## 6. Local Development

### Prerequisites
- Python 3.11+
- Node.js 20+
- PostgreSQL 16+ & Redis 7+ (or run via Docker)

### Backend Setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Or on Windows: .\.venv\Scripts\activate
pip install -r requirements-dev.txt

python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

The frontend will be accessible at `http://localhost:5173`.

---

## 7. Docker Development Stack

Start the entire environment using Docker Compose:

```bash
docker compose up --build
```

To run detached in background:
```bash
docker compose up -d --build
```

### Services Started:
- **PostgreSQL**: `localhost:5432` (Health-monitored)
- **Redis**: `localhost:6379` (Health-monitored)
- **Django REST API**: `http://localhost:8000`
- **Celery Worker**: Asynchronous background worker
- **React Frontend**: `http://localhost:5173`

Verify infrastructure health:
```bash
curl http://localhost:8000/api/health/
```

---

## 8. Running Backend Tests

```bash
cd backend
# Run test suite
pytest

# Run Django system checks
python manage.py check

# Run Ruff linter
ruff check .
```

---

## 9. Running Frontend Tests

```bash
cd frontend
# Run Vitest test suite
npm test

# Run TypeScript typecheck
npm run typecheck

# Run ESLint
npm run lint

# Run production build check
npm run build
```

---

## 10. Current Implementation Status

### Current Implementation:
**Phase 0 — Skeleton (Complete)**
- Full repository structure and separation of concerns established.
- Django 5.x booted with PostgreSQL and Redis configurations.
- Celery worker initialized with task auto-discovery and smoke task (`health_ping`).
- React 18 + TypeScript + Vite + Tailwind configured with TanStack Query.
- Health endpoint (`GET /api/health/`) operational and bound to frontend status UI.
- Automated tests, linting, typechecking, and Docker Compose stack validated.

**Phase 1 — Users, Teams & Identity Domain (Complete)**
- **Custom User Model**: Custom `User` extending `AbstractUser` configured via `AUTH_USER_MODEL = "users.User"`.
- **Team Model**: Operational ownership group with unique slug and active toggle.
- **TeamMembership Model**: Explicit join model linking `User` and `Team` with role assignment.
  - **Role Choices**: `ENGINEER`, `LEAD`, `RESPONDER`.
  - **Constraints**: Database-enforced `UniqueConstraint(fields=["user", "team"], name="unique_user_team_membership")`.
- **Deletion Policy**: Soft-deactivation preferred (`is_active = False`) to preserve historical auditability across incident timelines.
- **REST Endpoints**:
  - `GET /api/users/` (supports `?team=<team_id>`)
  - `GET /api/users/{id}/`
  - `GET /api/teams/` (annotated with `member_count`, supports `?is_active=true`)
  - `POST /api/teams/`
  - `GET /api/teams/{id}/`
  - `PATCH /api/teams/{id}/`
  - `GET /api/teams/{id}/members/` (supports `?is_active=true`)
  - `POST /api/team-memberships/`
  - `PATCH /api/team-memberships/{id}/`
  - `DELETE /api/team-memberships/{id}/` (soft-deactivates)
- **Demo Data Management**: Idempotent seeding command `python manage.py seed_demo`.

**Phase 2 — Services & Alert Ingestion (Complete)**
- **Service Model**: Monitored component owned by an operational `Team`.
  - Fields: `name`, `slug` (unique), `description`, `team` (FK to `users.Team`), `status` (`HEALTHY`, `DEGRADED`, `DOWN`), `is_active`.
  - Inactive team validation: Cannot bind an active service to an inactive team.
- **Alert Model**: Point-in-time operational signal targeting a `Service`.
  - Fields: `service` (FK to `services.Service`), `severity` (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), `message`, `source`, `fingerprint` (indexed SHA-256 hash), `metadata` (JSON), `received_at`, `created_at`.
- **Deterministic Alert Fingerprinting Foundation**:
  - Implemented in `apps/alerts/triage.py`.
  - Normalizes `source` (trimmed, lowercase) and `message` (trimmed, internal whitespace collapsed).
  - Deterministic digest: `SHA-256(f"{service_id}:{normalized_source}:{normalized_message}")`.
  - Invariant: Identical incoming alerts generate identical 64-character hex digests.
- **Alert Ingestion Pipeline**:
  - Encapsulated in `ingest_alert()` domain service (`apps/alerts/services.py`).
  - Strict validation: Inactive or nonexistent services rejected; severity canonicalized; non-blank message/source enforced.
  - Persists all incoming alerts; deduplication into active incidents is deferred to Phase 3.
- **REST Endpoints**:
  - `GET /api/services/` (supports `?team=<id>`, `?status=<HEALTHY|DEGRADED|DOWN>`, `?is_active=<true|false>`)
  - `POST /api/services/`
  - `GET /api/services/{id}/`
  - `PATCH /api/services/{id}/`
  - `GET /api/alerts/` (supports `?service=<id>`, `?severity=<LOW|MEDIUM|HIGH|CRITICAL>`, `?source=<source>`)
  - `POST /api/alerts/` (ingestion endpoint, returns 201 Created with fingerprint)
  - `GET /api/alerts/{id}/`
- **Demo Data Management**: Updated `seed_demo` to provision `Payment API`, `Authentication API`, and `Notification API` for `Backend Team`.

**Phase 3 — Incident Engine, Timeline & Alert Deduplication (Complete)**
- **Incident Model**: Core operational domain entity tracking outage lifecycles.
  - Fields: `service`, `title`, `severity`, `status` (`TRIGGERED`, `ACKNOWLEDGED`, `RESOLVED`), `fingerprint`, `assigned_user` (nullable), `triggered_at`, `acknowledged_at`, `resolved_at`, `created_at`, `updated_at`.
  - Database-Enforced Partial Unique Invariant: `UniqueConstraint(fields=["service", "fingerprint"], condition=Q(resolved_at__isnull=True), name="unique_active_incident_service_fingerprint")`. Ensures exactly one active incident per service and fingerprint.
- **IncidentEvent Model (Immutable Timeline)**:
  - Event types: `INCIDENT_TRIGGERED`, `ALERT_ATTACHED`, `INCIDENT_ACKNOWLEDGED`, `INCIDENT_RESOLVED`, `INCIDENT_REOPENED`.
  - Chronological ordering: `["created_at", "id"]`.
  - Strict append-only audit protection: Model-level validation prevents edits and deletions; `on_delete=models.PROTECT` prevents cascading deletion of incident histories.
- **Alert Triage & Deduplication**:
  - `triage_alert(alert) -> Incident`: Synchronously executed upon alert ingestion.
  - Active incident lookup: `service = alert.service AND fingerprint = alert.fingerprint AND resolved_at IS NULL`.
  - Concurrency safety: Uses `transaction.atomic()`, `select_for_update()`, and catches `IntegrityError` on the partial unique constraint to guarantee zero race condition duplicates.
  - Idempotent: Re-triaging an already-linked alert safely returns the incident without duplicate events.
- **State Machine Transitions**:
  - `TRIGGERED -> ACKNOWLEDGED`: Sets `acknowledged_at`, records `INCIDENT_ACKNOWLEDGED` (first write wins, subsequent duplicate acks are idempotent).
  - `TRIGGERED -> RESOLVED` / `ACKNOWLEDGED -> RESOLVED`: Sets `resolved_at`, records `INCIDENT_RESOLVED` (idempotent if already resolved).
  - `RESOLVED -> TRIGGERED`: Explicit reopen operation (`POST /api/incidents/{id}/reopen/`). Resets lifecycle timestamps (`triggered_at = now`, `acknowledged_at = null`, `resolved_at = null`), records `INCIDENT_REOPENED` with prior timestamps in metadata. Blocked with HTTP 409 Conflict if an active incident exists for the same service and fingerprint.
  - Direct status modification via generic `PATCH` and direct incident creation via `POST /api/incidents/` are strictly prohibited (HTTP 405).
- **Resolved Incident Policy**:
  - New matching alert arriving after resolution generates a **NEW Incident** (avoids ambiguous auto-reopening windows and keeps MTTA/MTTR metrics clean).
- **REST Endpoints**:
  - `GET /api/incidents/` (supports `?status=...`, `?service=...`, `?severity=...`, `?active=<true|false>`)
  - `GET /api/incidents/{id}/`
  - `GET /api/incidents/{id}/events/` (chronological read-only timeline)
  - `POST /api/incidents/{id}/acknowledge/`
  - `POST /api/incidents/{id}/resolve/`
  - `POST /api/incidents/{id}/reopen/`

**Phase 4 — Scheduling & Intelligent Routing (Complete)**
- **Schedule Model**: Operational on-call schedule owned by a `Team`.
  - Fields: `name`, `slug` (unique), `team` (FK to `users.Team`), `timezone` (validated IANA name e.g. `UTC`, `Asia/Kolkata`), `is_primary`, `is_active`, `created_at`, `updated_at`.
  - **Database Invariant**: `UniqueConstraint(fields=["team"], condition=Q(is_primary=True, is_active=True), name="unique_active_primary_schedule_per_team")`. Enforces exactly one active primary schedule per team for deterministic incident routing.
- **ScheduleRotation Model**: Concrete on-call shift window assigned to an active team member.
  - Fields: `schedule` (FK), `user` (FK to `AUTH_USER_MODEL`), `start_time` (UTC datetime), `end_time` (UTC datetime), `is_override` (boolean), `created_at`, `updated_at`.
  - **Database Constraint**: `CheckConstraint(condition=Q(end_time__gt=F("start_time")), name="rotation_end_time_after_start_time")`.
  - **UTC & Timezone Rules**: All rotation timestamps are strictly validated as timezone-aware and persisted in UTC.
  - **Half-Open Intervals**: Operates on `start_time <= timestamp < end_time` semantics, eliminating boundary ambiguity at exact shift handoffs (e.g. 17:00:00).
  - **User Eligibility**: Only active users with an active `TeamMembership` in the schedule's owning team can be assigned to a rotation (`IneligibleUserError`).
  - **Overlap Validation**: Base-to-base and override-to-override overlaps on the same schedule are rejected (`RotationOverlapError`). Override-to-base overlaps are allowed because overrides intentionally replace base shifts.
- **Deterministic On-Call Resolution (`apps/scheduling/services.py`)**:
  - `get_on_call(schedule, timestamp) -> User | None`: Pure function requiring an explicit timezone-aware timestamp (naive datetimes rejected with `InvalidTimestampError`).
  - **Override Precedence**: Active overrides strictly supersede base rotations.
  - `get_on_call_assignment(schedule, timestamp) -> dict | None`: Returns metadata `{user, rotation, source: "override" | "base"}`.
  - `get_routing_schedule(service) -> Schedule | None`: Resolves operational schedule via `Service -> Team -> Primary Active Schedule`.
- **Automatic Incident Routing (`assign_incident_on_creation`)**:
  - Triggered during `triage_alert()` ONLY when a new incident is created.
  - Resolves responder using `incident.triggered_at` for reproducible, deterministic assignments.
  - Persists `incident.assigned_user` and appends `RESPONDER_ASSIGNED` event to the incident timeline.
  - **Assignment Stability**: Duplicate alerts attaching to an active incident (`ALERT_ATTACHED`) preserve the existing assignee and never recompute routing, even if on-call shifts rotate mid-incident.
  - **No-Responder Policy**: If a team has no active primary schedule or the schedule has no active rotation at `triggered_at`, the incident is created safely with `assigned_user = None` and a `ROUTING_UNAVAILABLE` event is appended to the timeline (no 500s, no arbitrary fallbacks).
  - **Idempotency**: Calling assignment logic multiple times preserves existing assignee without generating duplicate events.
- **REST Endpoints**:
  - `GET /api/schedules/` (supports `?team=<id>`, `?is_active=<true|false>`, `?is_primary=<true|false>`)
  - `POST /api/schedules/`
  - `GET /api/schedules/{id}/`
  - `PATCH /api/schedules/{id}/`
  - `GET /api/schedules/{id}/on-call/` (supports `?at=<ISO_8601>`, returns on-call user and source)
  - `GET /api/schedule-rotations/` (supports `?schedule=<id>`, `?user=<id>`, `?is_override=<true|false>`)
  - `POST /api/schedule-rotations/`
  - `GET /api/schedule-rotations/{id}/`
  - `PATCH /api/schedule-rotations/{id}/`
  - `DELETE /api/schedule-rotations/{id}/`
- **Admin & Demo Data**:
  - Registered `Schedule` and `ScheduleRotation` in Django admin.
  - Extended `python manage.py seed_demo` to seed `Backend Primary` schedule with base rotations for Alice and Bob, plus an override.

**Phase 5 — Escalation, Notifications & Backend Automation (Complete)**
- **EscalationPolicy & EscalationLevel Models**:
  - `EscalationPolicy`: Tiered operational escalation policy owned by a `Team` (`name`, `slug`, `team`, `is_active`).
  - `EscalationLevel`: Step within a policy defining target type (`CURRENT_ON_CALL` or `USER`), `target_user` (validated active member of policy team), and `wait_minutes` (non-negative delay before subsequent escalation).
  - **Database Constraints**: `UniqueConstraint(fields=["policy", "order"], name="unique_policy_level_order")` enforcing strict sequential ordering. Deletion protection (`on_delete=models.PROTECT`) prevents destroying active incident escalation paths.
- **Service Integration**: Added `Service.escalation_policy` foreign key with `on_delete=models.PROTECT`.
- **Durable Incident Escalation State**:
  - `Incident.current_escalation_level`: Points to the active `EscalationLevel`.
  - `Incident.automation_generation`: Monotonically increasing version (`PositiveIntegerField(default=1)`) incremented on incident reopen to prevent stale asynchronous tasks from older lifecycles from mutating reopened incidents.
- **Notification Domain & Provider Abstraction**:
  - `Notification` model: Durable, auditable record tracking dispatch status (`PENDING`, `SENT`, `FAILED`), delivery attempts (`attempt_count`), timestamps (`sent_at`, `failed_at`), and `last_error`.
  - **Deterministic Idempotency Key**: `dedupe_key = f"inc:{incident.id}:lvl:{level_id}:gen:{generation}:usr:{recipient_id}:ch:{channel}"` backed by a database unique constraint. Prevents duplicate notifications during Celery retries or concurrent dispatches.
  - `BaseNotificationProvider`: Extensible interface decoupling orchestration from external vendor SDKs.
  - `SimulatedEmailProvider`: In-memory simulated email delivery with deterministic fault injection capabilities. Intentionally does NOT connect to real external SMTP/SendGrid/Twilio.
- **Celery Tasks & Asynchronous Orchestration**:
  - `dispatch_notification(notification_id)`: Asynchronously delivers messages via provider with bounded retries (`max_retries=3`). Commits DB attempt updates before raising Celery retry to avoid rollback of failure history.
  - `check_and_escalate(incident_id, expected_level_id, expected_generation)`: Delayed Celery task scheduled via `transaction.on_commit(countdown=wait_minutes * 60)`.
    - **Concurrency & Idempotency Safeguards**:
      1. Live state reload under atomic row lock (`select_for_update()`).
      2. Status check: Exits harmlessly if status is not `TRIGGERED` (acknowledgement or resolution halts escalation cleanly without Celery task cancellation).
      3. Generation check: Exits harmlessly if `incident.automation_generation != expected_generation` (invalidates stale tasks from prior reopen cycles).
      4. Expected-level guard: Exits harmlessly if `incident.current_escalation_level_id != expected_level_id` (prevents duplicate worker executions from skipping levels).
      5. Final-level exhaustion: If no further levels exist, appends `ESCALATION_EXHAUSTED` event exactly once and halts without re-wrapping or erroring.
- **Timeline Audit Entries**: Added `ESCALATION_STARTED`, `INCIDENT_ESCALATED`, `ESCALATION_EXHAUSTED`, and `ESCALATION_TARGET_UNAVAILABLE` to `IncidentEvent.EventType`.
- **Lifecycle Transitions**:
  - `reopen_incident`: Explicitly transitions `RESOLVED -> TRIGGERED`, increments `automation_generation += 1`, resets `current_escalation_level = Level 1`, and restarts escalation automation.
- **REST Endpoints**:
  - `GET /api/escalation-policies/` (supports `?team=<id>`, `?is_active=<true|false>`)
  - `POST /api/escalation-policies/`
  - `GET /api/escalation-policies/{id}/`
  - `PATCH /api/escalation-policies/{id}/`
  - `GET /api/escalation-levels/` (supports `?policy=<id>`, `?target_type=<type>`)
  - `POST /api/escalation-levels/`
  - `GET /api/escalation-levels/{id}/`
  - `PATCH /api/escalation-levels/{id}/`
  - `GET /api/notifications/` (read-only, supports `?incident=<id>`, `?recipient=<id>`, `?status=<PENDING|SENT|FAILED>`, `?channel=EMAIL`)
  - `GET /api/notifications/{id}/`
  - `POST /api/notifications/{id}/retry/` (re-enqueues FAILED notifications)
- **Admin & Demo Data**:
  - Registered `EscalationPolicy` (with `EscalationLevelInline`), `EscalationLevel`, and `Notification` in Django admin.
  - Extended `seed_demo` with `Backend Critical Policy` (Level 1: CURRENT_ON_CALL, wait 5 min; Level 2: Bob, wait 10 min) linked to `Payment API`.

### Next Phase:
- Phase 6 — Frontend Foundation (application shell, routing, typed API client, TanStack Query integration, shared components, loading/error states)
- Phase 7 — Analytics & Metrics (MTTA/MTTR calculations)

