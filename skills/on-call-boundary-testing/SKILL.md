---
name: on-call-boundary-testing
description: Instructions and procedures for verifying schedule rotation intervals, override precedence, midnight UTC crossing, and daylight saving time resilience.
---

# On-Call Boundary Testing Skill

## Purpose
This skill defines the procedures to test and audit on-call responder resolution across shift boundaries, overrides, and timezone transitions in the Incident Management Platform.

## Core Rules & Invariants
1. **Half-Open Intervals**:
   - All schedule rotations and overrides use half-open intervals: `[start_time, end_time)`.
   - A query at `start_time` matches the rotation.
   - A query at `end_time` does not match the rotation (transitions to the next interval or returns `None`).
2. **Override Precedence**:
   - Active overrides take strict precedence over base rotations.
   - If an override is active at timestamp `T`, the override's user is returned even if a base rotation also covers `T`.
3. **UTC Invariance & Timezones**:
   - All timestamps in PostgreSQL are stored with UTC timezone awareness (`timestamptz`).
   - DST shifts (e.g. America/New_York) do not cause gaps or double-counted shifts because resolution occurs in continuous UTC time.
4. **Historical Assignment Immutability**:
   - Deactivating a user or modifying an on-call schedule never retroactively mutates `incident.assigned_user_id` on existing incidents.

## Verification Procedures
1. Set up a base rotation from `09:00:00Z` to `17:00:00Z` for User A, and `17:00:00Z` to `01:00:00Z` (next day) for User B.
2. Query on-call at `08:59:59.999999Z` -> verify `None`.
3. Query on-call at `09:00:00.000000Z` -> verify User A.
4. Query on-call at `16:59:59.999999Z` -> verify User A.
5. Query on-call at `17:00:00.000000Z` -> verify User B.
6. Query on-call at `00:30:00.000000Z` (midnight-crossing) -> verify User B.
7. Query on-call at `01:00:00.000000Z` -> verify `None`.
8. Create an override for User C from `12:00:00Z` to `14:00:00Z`.
9. Query at `12:30:00Z` -> verify User C is returned with `is_override=True`.
