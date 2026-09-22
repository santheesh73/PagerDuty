# End-to-End (E2E) Integration & Workflow Verification

This directory contains the end-to-end integration and user workflow verification suite for the Incident Management Platform.

## Test Suite Overview

`test_e2e_workflows.py` executes directly against the running platform via HTTP REST API and verifies the core operational workflows across all system tiers:

- **Scenario 1: Incident Responder Workflow**
  - Alert ingestion (`POST /api/alerts/`) creates an operational incident with status `TRIGGERED`
  - Timeline audit trail records `INCIDENT_TRIGGERED` and `ALERT_ATTACHED`
  - Prohibited direct mutations are rejected (`POST /api/incidents/` -> 405, `PATCH /api/incidents/{id}/` -> 405)
  - Responder acknowledges incident (`POST /api/incidents/{id}/acknowledge/`) -> status transitions to `ACKNOWLEDGED`
  - Responder resolves incident (`POST /api/incidents/{id}/resolve/`) -> status transitions to `RESOLVED`
  - Invalid state transitions rejected (`POST /api/incidents/{id}/acknowledge/` after resolve -> 409 Conflict)

- **Scenario 2: Configuration Affects Runtime Behavior**
  - Evaluates on-call responder transitions across half-open `[start, end)` intervals
  - Verifies exact 1-second boundary transitions (`11:59:59Z` base -> `12:00:00Z` override -> `13:59:59Z` override -> `14:00:00Z` base)
  - Proves that schedule overrides take immediate effect on operational routing without platform restarts

- **Scenario 3: Escalation Progression & Contract Verification**
  - Inspects escalation policy hierarchy and tiered level definitions
  - Verifies cross-team policy validation (`POST /api/services/` with mismatched escalation policy team -> 400 Bad Request)
  - Verifies standard error envelope consistency on 404
  - Verifies analytics summary null semantics

## Execution

Ensure the Docker stack is running:
```bash
docker compose up -d
```

Run the E2E verification suite:
```bash
python e2e/test_e2e_workflows.py
```
