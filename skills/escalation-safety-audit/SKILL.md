---
name: escalation-safety-audit
description: Instructions and audit procedures for testing asynchronous Celery escalation, state guards, duplicate task handling, and automation generation epochs.
---

# Escalation Safety Audit Skill

## Purpose
This skill defines the verification procedures for testing asynchronous Celery escalation tasks, ensuring that retries, races, and out-of-order executions never lead to improper incident state transitions or duplicate notifications.

## Core Rules & Invariants
1. **The Three Safety Guards**:
   Before any Celery escalation task mutates state, it reloads the incident with `select_for_update()` and verifies:
   - **Guard 1 (Live Status)**: `incident.status == IncidentStatus.TRIGGERED`. If acknowledged or resolved, abort immediately.
   - **Guard 2 (Expected Level)**: `incident.current_escalation_level == expected_level`. If another task or manual action already advanced the level, abort immediately.
   - **Guard 3 (Automation Generation Epoch)**: `incident.automation_generation == expected_generation`. If the incident was resolved and reopened, older queued tasks are discarded as no-ops.
2. **Terminal State Immutability**:
   - Resolving an incident prevents any queued or concurrent escalation tasks from modifying the incident.
3. **Bounded Retries & Idempotent Notifications**:
   - Notification failures retry with exponential backoff up to 3 times on the same notification record (`attempt_count`).
   - Dedupe keys (`f"inc_{incident_id}_lvl_{level_number}_{target}"`) prevent redundant notification creations.

## Verification Procedures
1. Trigger an incident with an escalation policy containing 2 or more levels.
2. Simulate duplicate Celery execution by firing `check_and_escalate(incident_id, expected_level=1, expected_generation=1)` 5 times simultaneously.
3. Verify the incident advances to Level 2 exactly once.
4. Verify remaining 4 executions return `False` without logging extra events or creating extra notifications.
5. Resolve the incident.
6. Attempt executing `check_and_escalate(incident_id, expected_level=2, expected_generation=1)`.
7. Verify immediate no-op return.
8. Reopen the incident (increments `automation_generation` to 2).
9. Attempt firing a stale task with `expected_generation=1`.
10. Verify task is cleanly discarded.
