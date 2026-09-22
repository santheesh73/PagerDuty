# Testing Strategy & Verification Guide

This document outlines the testing architecture, test suites, failure injection scenarios, and commands used to verify the platform's reliability.

---

## 1. Test Architecture Overview

The platform uses a layered testing strategy to prove correctness across unit, integration, concurrency, failure injection, and end-to-end boundaries:

```
┌────────────────────────────────────────────────────────┐
│  End-to-End Integration Suite (e2e/test_e2e_workflows) │
├────────────────────────────────────────────────────────┤
│  Frontend Vitest Suite (73 tests: components & hooks)  │
├────────────────────────────────────────────────────────┤
│  Backend Pytest Hardening & Races (test_races.py, etc.)│
├────────────────────────────────────────────────────────┤
│  Backend Pytest Domain & API Suite (218 tests total)   │
└────────────────────────────────────────────────────────┘
```

---

## 2. Backend Test Suites (218 Tests)

All backend tests run via `pytest` with `pytest-django` against an isolated PostgreSQL database.

### Key Test Categories
1. **Domain & API Contracts**:
   - `apps/users/tests/`: Custom user creation, team memberships, role validations.
   - `apps/services/tests/`: Service registration, team mismatches, escalation policy bindings.
   - `apps/alerts/tests/`: Fingerprint normalization, deterministic hashing, triage entry.
   - `apps/incidents/tests/`: State transitions (`TRIGGERED` -> `ACKNOWLEDGED` -> `RESOLVED`), reopen cycles.
   - `apps/scheduling/tests/`: Schedule rotations, override precedence, responder lookup.
   - `apps/escalation/tests/`: Multi-level policies, level ordering, Celery task registration.
   - `apps/notifications/tests/`: Simulated delivery providers, dedupe keys.
   - `apps/analytics/tests/`: MTTA and MTTR calculations, team aggregations.
2. **Concurrency & Race Conditions (`apps/incidents/tests/test_races.py`)**:
   - `test_high_concurrency_alert_ingestion_10_threads`: 10 threads submitting the same alert converge on 1 incident.
   - `test_multi_user_simultaneous_acknowledgement_3_actors`: First-write-wins; exactly 1 `INCIDENT_ACKNOWLEDGED` event.
   - `test_concurrent_acknowledge_and_resolve_race`: Resolving wins; guaranteed `acknowledged_at <= resolved_at`.
   - `test_resolve_vs_escalation_race`: Row locks prevent escalation after committed resolution.
3. **Escalation Failure Modes (`apps/escalation/tests/test_failure_modes.py`)**:
   - `test_duplicate_celery_task_execution_idempotency_10x`: 10 identical Celery tasks advance exactly 1 level; 9 no-op.
   - `test_task_execution_on_resolved_incident_clean_noop`: Celery task aborts safely on resolved incidents.
   - `test_stale_generation_task_execution_prevented`: Stale generation tasks from prior open states are dropped.
   - `test_cascade_deletion_prevention_on_policies_and_levels`: `ProtectedError` prevents deletion of referenced policies.
4. **Schedule Boundaries & DST (`apps/scheduling/tests/test_boundaries.py`)**:
   - Sub-second precision tests across half-open `[start, end)` boundaries.
   - Shifts crossing midnight UTC (`17:00` to `01:00` next day).
   - Daylight Saving Time (DST) Spring-Forward transitions.
5. **Notification Retry Exhaustion (`apps/notifications/tests/test_retry_failures.py`)**:
   - Bounded retries: 2 failures followed by 1 success updates the same database row (`attempt_count=3`).
   - Permanent failure: 4 persistent failures transition status to `FAILED` without retry storms.

### Execution Command
```bash
# Inside Docker container
docker compose exec -T backend pytest

# Or directly on host
cd backend
pytest
```

---

## 3. Frontend Test Suite (73 Tests)

The frontend test suite uses **Vitest**, **React Testing Library**, and **JSDOM**.

### Coverage Areas
- **API Client**: Request interceptors, error transformations, parameter serialization.
- **Custom Hooks**: `useIncidents`, `useServices`, `useOnCall`, `useEscalationPolicies`, `useAnalytics`.
- **Components & Pages**:
  - `Dashboard.test.tsx`: KPI widgets, active incident counters.
  - `Incidents.test.tsx`: Filter by status and severity, table rendering.
  - `IncidentDetail.test.tsx`: Responder card, actions panel, immutable timeline events.
  - `OnCallSchedule.test.tsx`: Override badges, live responder card.
  - `Analytics.test.tsx`: MTTA/MTTR cards, severity distribution.
  - `ErrorBoundary.test.tsx`: Graceful recovery from uncaught render exceptions.

### Execution Commands
```bash
cd frontend
npm run typecheck   # TypeScript check (0 errors)
npm run lint        # ESLint check (0 errors/warnings)
npm test            # Run Vitest test runner (73 passed)
npm run build       # Production bundle build
```

---

## 4. End-to-End Workflow Verification

The `e2e/test_e2e_workflows.py` script exercises live interactions against the running Docker stack:
1. **Scenario 1: Incident Responder Workflow**: Ingests alert -> Verifies incident trigger -> Checks timeline -> Verifies direct mutation 405 -> Acknowledges -> Resolves -> Verifies 409 on invalid transition.
2. **Scenario 2: Configuration Affects Runtime**: Verifies on-call rotations across base and override intervals.
3. **Scenario 3: Escalation & Contracts**: Verifies policy levels, cross-team assignment rejection, and analytics aggregations.

### Execution Command
```bash
python e2e/test_e2e_workflows.py
```
