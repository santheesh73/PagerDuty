# Development Transcript: Phase 4: On-Call Scheduling & Routing

**Phase**: Phase 4  
**Step Range**: 953 to 1308  
**Timestamp**: 2026-09-21T05:57:27Z  

---

## 1. Initial Directive & User Request
`markdown
<USER_REQUEST>
# MASTER PROMPT — PHASE 4
# Incident Management Platform
# Phase 4: Scheduling & Intelligent Routing

You are acting as the senior backend engineer responsible for Phase 4 of a
production-quality incident management platform.

The following phases are already complete and protected:

Phase 0
- project skeleton
- Docker
- PostgreSQL
- Redis
- Celery
- Django/DRF
- React/Vite
- test foundation

Phase 1
- User
- Team
- TeamMembership

Phase 2
- Service
- Alert
- alert ingestion
- deterministic fingerprinting

Phase 3
- Incident
- IncidentEvent
- triage_alert()
- alert-to-incident deduplication
- concurrency-safe active incident uniqueness
- acknowledge
- resolve
- reopen
- immutable incident timeline

DO NOT redesign any previous phase.

DO NOT change the core architecture.

Phase 4 introduces:

- Schedule
- ScheduleRotation
- schedule overrides
- deterministic get_on_call(schedule, timestamp)
- service/team schedule resolution
- automatic responder assignment
- assignment timeline events
- manual reassignment only if required and explicitly controlled

Phase 4 DOES NOT implement:

- EscalationPolicy
- EscalationLevel
- Celery escalation timers
- notification delivery
- retries
- analytics
- operational frontend

Those belong to Phase 5+.

======================================================================
0. FIXED ARCHITECTURE — DO NOT CHANGE
======================================================================

Architecture remains:

React 18 + TypeScript + Vite
        |
        | REST / JSON
        v
Django 5.x + Django REST Framework
        |
        +----------------------> PostgreSQL 15+
        |
        v
Redis 7.x
        |
        v
Celery 5.x

Django owns:
- scheduling rules
- on-call calculation
- incident assignment
- validation
- REST APIs

PostgreSQL owns:
- schedule persistence
- rotation persistence
- incident assignment persistence

Redis + Celery:
- remain available
- no 
<truncated 35771 bytes>
 Flow

Show:

Incident
  |
Service
  |
Team
  |
Schedule
  |
get_on_call()
  |
assigned_user

## Time Semantics

Document:

UTC storage
half-open interval
override precedence

## Assignment Policy

Document:

new Incident:
route once

existing active Incident:
keep existing assignee

## No-On-Call Policy

Document actual behavior.

## API Endpoints

List actual routes.

## Database Constraints

List actual constraints.

## Migrations

Report actual results.

## Tests

Backend:
X passed / Y failed

Scheduling:
X passed / Y failed

Routing:
X passed / Y failed

Frontend regression:
X passed / Y failed

## Docker Validation

PostgreSQL:
Redis:
Django:
Celery:
React:

## Phase 0-3 Regression

Report actual results.

## Architectural Changes

Expected:

None.

If changed, explain why.

## Phase Boundary Confirmation

Explicitly confirm:

"No EscalationPolicy, EscalationLevel, Notification workflow,
Celery escalation timers or Analytics business logic was implemented."

## Known Issues

Only real issues.

## Next Phase

Phase 5 — Escalation & Automation:
- EscalationPolicy
- EscalationLevel
- notifications
- Celery delayed escalation
- retries
- idempotency

======================================================================
FINAL DIRECTIVE
======================================================================

Implement Phase 4 completely.

Work like a senior production engineer.

Do not redesign the system.

Do not change the core architecture.

Do not start Phase 5.

The key outcomes are:

1. deterministic on-call calculation
2. UTC-safe scheduling
3. override precedence
4. unambiguous boundaries
5. automatic assignment of NEW incidents
6. assignment stability for existing incidents
7. graceful unassigned behavior

Get these correct before moving to escalation automation.
... [Full request truncated for document readability]
`

---

## 2. Phase Execution & Final Response
## Phase 4 Status

**COMPLETE**

---

## Implemented

### Schedule:
- Model [`Schedule`](file:///d:/Projects/PagerDuty/backend/apps/scheduling/models.py): Attached to [`Team`](file:///d:/Projects/PagerDuty/backend/apps/users/models.py), IANA `timezone`, `is_primary`, `is_active`.
- Constraint: `UniqueConstraint(fields=["team"], condition=Q(is_primary=True, is_active=True), name="unique_active_primary_schedule_per_team")`.
- Validation: Validates timezone via `zoneinfo.available_timezones()`, prevents associating active schedules with inactive teams.
- API & Admin: Full CRUD via [`ScheduleViewSet`](file:///d:/Projects/PagerDuty/backend/apps/scheduling/views.py) with filters (`team`, `is_active`, `is_primary`) and Django admin registration.

### ScheduleRotation:
- Model [`ScheduleRotation`](file:///d:/Projects/PagerDuty/backend/apps/scheduling/models.py): FK to `Schedule` and `User`, `start_time`, `end_time`, `is_override`.
- Constraint: `CheckConstraint(condition=Q(end_time__gt=F("start_time")), name="rotation_end_time_after_start_time")`.
- Validation: Requires timezone-aware datetimes, active user with active [`TeamMembership`](file:///d:/Projects/PagerDuty/backend/apps/users/models.py) in the schedule's team (`IneligibleUserError`), and overlap checks (`RotationOverlapError`).
- API & Admin: CRUD and delete via [`ScheduleRotationViewSet`](file:///d:/Projects/PagerDuty/backend/apps/scheduling/views.py) and Django admin.

### Routing:
- Calculation [`get_on_call()`](file:///d:/Projects/PagerDuty/backend/apps/scheduling/services.py): Pure function accepting explicit timezone-aware timestamps (`InvalidTimestampError` on naive).
- Precedence: Overrides strictly supersede base rotations.
- Resolution: [`get_routing_schedule()`](file:///d:/Projects/PagerDuty/backend/apps/scheduling/services.py) resolves `Service -> Team -> Primary Active Schedule`.
- API: `GET /api/schedules/{id}/on-call/?at=<ISO_8601>`.

### Incident Integration:
- Automated assignment [`assign_incident_on_creation()`](file:///d:/Projects/PagerDuty/
<truncated 2957 bytes>
r_team` on `Schedule` (`UniqueConstraint(fields=["team"], condition=Q(is_primary=True, is_active=True))`).
2. `rotation_end_time_after_start_time` on `ScheduleRotation` (`CheckConstraint(condition=Q(end_time__gt=F("start_time")))`).

---

## Migrations

- `incidents.0002_alter_incidentevent_event_type`: Added `RESPONDER_ASSIGNED` and `ROUTING_UNAVAILABLE`.
- `scheduling.0001_initial`: Created tables `scheduling_schedule` and `scheduling_schedulerotation` with constraints and indexes.
- `python manage.py makemigrations --check` reports **No changes detected**.

---

## Tests

- **Backend Total**: 124 passed / 0 failed
- **Scheduling**: 42 passed / 0 failed
  - `test_models.py`: 14 passed
  - `test_get_on_call.py`: 6 passed
  - `test_overrides.py`: 2 passed
  - `test_routing.py`: 6 passed
  - `test_api.py`: 7 passed
  - `test_golden_acceptance.py`: 7 passed (Scenarios A through G)
- **Frontend Regression**: 5 passed / 0 failed (TypeScript, ESLint, and Vite build green).

---

## Docker Validation

- **PostgreSQL 16**: Healthy
- **Redis 7**: Healthy
- **Django 5.1**: Healthy, `GET /api/health/` returns `{"status":"ok","dependencies":{"database":"ok","redis":"ok"}}`
- **Celery 5.4**: Healthy, `health_ping` task registered
- **React 18**: Built and serving

---

## Phase 0-3 Regression

- Phase 0 (Health, settings, Docker, Celery): 100% green
- Phase 1 (User, Team, TeamMembership): 100% green
- Phase 2 (Service, Alert, Fingerprinting): 100% green
- Phase 3 (Incident, IncidentEvent, Triage, Dedup, State transitions): 100% green

---

## Architectural Changes

**None.** Architecture remains Django REST Framework + PostgreSQL + Redis + Celery + React.

---

## Phase Boundary Confirmation

> "No EscalationPolicy, EscalationLevel, Notification workflow, Celery escalation timers or Analytics business logic was implemented."

---

## Known Issues

**None.**

---

## Next Phase

**Phase 5 — Escalation & Automation**:
- `EscalationPolicy`
- `EscalationLevel`
- notifications
- Celery delayed escalation
- retries
- idempotency
