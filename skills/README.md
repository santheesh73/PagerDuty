# Skills Directory

This directory contains repository-specific AI engineering skills, operational runbooks, and automated verification procedures authored during the development and hardening of the Incident Management Platform.

## Available Skills

| Skill | Description | Location |
| :--- | :--- | :--- |
| **`incident-triage-verification`** | Procedures for verifying alert normalization, SHA-256 fingerprinting, atomic triage, and active incident deduplication. | [`skills/incident-triage-verification/SKILL.md`](./incident-triage-verification/SKILL.md) |
| **`on-call-boundary-testing`** | Invariants and test matrices for half-open schedule rotations `[start, end)`, override precedence, midnight UTC crossing, and DST resilience. | [`skills/on-call-boundary-testing/SKILL.md`](./on-call-boundary-testing/SKILL.md) |
| **`escalation-safety-audit`** | Audit procedures for Celery escalation safety guards (`live status`, `expected level`, `automation_generation` epoch), duplicate executions, and bounded retries. | [`skills/escalation-safety-audit/SKILL.md`](./escalation-safety-audit/SKILL.md) |
| **`full-system-golden-flow`** | End-to-end verification checklist and workflow validation covering Alert Ingestion -> Responder Routing -> Notification -> Delayed Escalation -> Acknowledge -> Resolve -> Timeline -> Analytics. | [`skills/full-system-golden-flow/SKILL.md`](./full-system-golden-flow/SKILL.md) |
