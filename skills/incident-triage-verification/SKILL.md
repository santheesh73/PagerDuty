---
name: incident-triage-verification
description: Instructions and verification procedures for testing alert normalization, deterministic fingerprinting, atomic alert triage, and active incident deduplication.
---

# Incident Triage Verification Skill

## Purpose
This skill defines the procedures to verify the integrity and idempotency of alert ingestion and incident deduplication in the Incident Management Platform.

## Core Rules & Invariants
1. **Deterministic Fingerprinting**:
   - Source is lowercased and stripped.
   - Message has whitespace collapsed and stripped.
   - SHA-256 digest is calculated over `f"{service.id}:{normalized_source}:{normalized_message}"`.
   - Fingerprint must match `^[a-f0-9]{64}$`.
2. **One Active Incident Guarantee**:
   - The platform enforces `UniqueConstraint(fields=["service", "fingerprint"], condition=Q(resolved_at__isnull=True))` at the database level.
   - Incoming alerts matching an active incident's fingerprint must attach to the existing incident and record an `ALERT_ATTACHED` timeline event.
   - No new incident may be triggered while an unresolved incident exists with the same fingerprint.
3. **Concurrency Safety**:
   - `triage_alert()` runs inside an atomic transaction using `select_for_update()` and handles `IntegrityError` races cleanly.

## Verification Procedures
1. Submit an alert payload to `POST /api/alerts/`:
   ```json
   {
     "service": 1,
     "severity": "CRITICAL",
     "message": "High CPU utilization > 95%",
     "source": "Prometheus"
   }
   ```
2. Verify response status is `201 Created` with a 64-character hex fingerprint.
3. Query `GET /api/incidents/?service=1` and verify the incident status is `TRIGGERED`.
4. Ingest the same alert payload again.
5. Verify no second incident is created, alert count increments, and an `ALERT_ATTACHED` event is present on the incident timeline (`GET /api/incidents/{id}/timeline/`).
