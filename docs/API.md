# REST API Specification & Contract Reference

The Incident Management Platform exposes a standard, predictable JSON REST API governed by Django REST Framework.

**Base URL**: `http://localhost:8000/api`

---

## 1. Standard Error Responses

All API errors return consistent JSON responses with standard HTTP status codes:

- **`400 Bad Request`**: Validation failure or malformed payload.
  ```json
  {
    "service": ["This field is required."],
    "severity": ["\"INVALID\" is not a valid choice."]
  }
  ```
- **`404 Not Found`**: Resource does not exist.
  ```json
  {
    "detail": "Not found."
  }
  ```
- **`405 Method Not Allowed`**: Direct modification on read-only views or prohibited methods.
  ```json
  {
    "detail": "Method \"POST\" not allowed."
  }
  ```
- **`409 Conflict`**: Invalid state machine transition (e.g. attempting to acknowledge an already resolved incident).
  ```json
  {
    "error": "Incident is already resolved."
  }
  ```

---

## 2. Core API Endpoints

### 2.1 System Health
- **`GET /api/health/`**
  - **Description**: Returns real-time health checks for PostgreSQL and Redis.
  - **Response (200 OK)**:
    ```json
    {
      "status": "ok",
      "dependencies": {
        "database": "ok",
        "redis": "ok"
      }
    }
    ```

### 2.2 Alerts Ingestion
- **`POST /api/alerts/`**
  - **Description**: Ingests an incoming alert, normalizes source and message, calculates a deterministic SHA-256 fingerprint, and triggers triage.
  - **Request Body**:
    ```json
    {
      "service": 1,
      "severity": "CRITICAL",
      "message": "Database connection pool exhausted",
      "source": "Datadog",
      "metadata": { "pool_size": 100, "utilization": 1.0 }
    }
    ```
  - **Response (201 Created)**:
    ```json
    {
      "id": 42,
      "service": 1,
      "severity": "CRITICAL",
      "message": "Database connection pool exhausted",
      "source": "datadog",
      "fingerprint": "a3f5...",
      "received_at": "2026-09-22T10:00:00Z"
    }
    ```

### 2.3 Incidents & State Transitions
- **`GET /api/incidents/`**
  - **Filters**: `?status=TRIGGERED|ACKNOWLEDGED|RESOLVED`, `?severity=CRITICAL|HIGH|MEDIUM|LOW`, `?service=<id>`
  - **Response (200 OK)**: List of incident summaries.
- **`GET /api/incidents/{id}/`**
  - **Description**: Detailed incident object including assigned responder, current escalation level, and timing.
- **`POST /api/incidents/{id}/acknowledge/`**
  - **Description**: Transitions status from `TRIGGERED` to `ACKNOWLEDGED`. Idempotent if already acknowledged.
  - **Response (200 OK)**: Updated incident representation.
- **`POST /api/incidents/{id}/resolve/`**
  - **Description**: Transitions status to `RESOLVED`, sets `resolved_at`, and halts any pending escalation timers. Idempotent if already resolved.
  - **Response (200 OK)**: Updated incident representation.
- **`POST /api/incidents/{id}/reopen/`**
  - **Description**: Reopens a `RESOLVED` incident, increments `automation_generation`, and re-starts escalation.
  - **Response (200 OK)**: Updated incident representation.
- **`GET /api/incidents/{id}/timeline/`**
  - **Description**: Chronological, immutable audit trail of all events for this incident.

### 2.4 On-Call Scheduling
- **`GET /api/schedules/`**
  - **Description**: List configured team on-call schedules.
- **`GET /api/schedules/{id}/on-call/`**
  - **Query Params**: Optional `?at=ISO_8601_TIMESTAMP` (defaults to now).
  - **Response (200 OK)**:
    ```json
    {
      "schedule_id": 1,
      "user": {
        "id": 2,
        "username": "alice",
        "email": "alice@example.com"
      },
      "is_override": false,
      "evaluated_at": "2026-09-22T10:00:00Z"
    }
    ```

### 2.5 Escalation Policies
- **`GET /api/escalation-policies/`**
  - **Description**: List escalation policies with nested escalation levels and delay timers.
- **`POST /api/escalation-policies/{id}/reorder_levels/`**
  - **Description**: Atomically updates the step sequence of escalation levels.

### 2.6 Analytics
- **`GET /api/analytics/summary/`**
  - **Description**: Aggregates total incidents, active incidents, acknowledged counts, resolved counts, Mean Time to Acknowledge (MTTA in seconds), and Mean Time to Resolve (MTTR in seconds).
