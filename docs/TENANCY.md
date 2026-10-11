# Tenancy

**Decision: one organisation per deployment.** Pulse is single-tenant. A deployment holds one organisation's teams, people and services. It does not isolate several customers from each other. To serve two organisations, run two deployments, each with its own database, secrets and integration keys.

## What is isolated: teams

Inside the organisation, **teams** are the boundary, and it is enforced on every endpoint:

- Services, escalation policies, schedules, incidents, alerts, timelines, notifications and analytics are scoped to the teams you belong to. The user directory shows only your teammates, and the audit log shows only the teams you administer.
- Each membership has a role per team: **viewer** (read), **responder** (act on incidents), **admin** (configure). The same person can hold different roles on different teams.
- Someone outside a team gets **404, not 403**, for that team's objects, so ids can't be probed.
- `backend/apps/core/tests/test_tenant_matrix.py` walks the real URL table. Every route and method is called as a member of another team and must return 403/404, change nothing, and leak nothing in list responses. A new endpoint fails that test until it is classified. More cases are in `test_tenant_isolation.py`, and the guarantee is I16 in [INVARIANTS.md](INVARIANTS.md).

## What is global

These are deployment-wide by design, which is why one deployment is one organisation:

- **User accounts.** An email address is unique across the deployment, and a person signs in once and sees all of their teams.
- **Staff users** (`is_staff`) act as admin on **every** team and see every audit event. They are the organisation's operators. With `REQUIRE_MFA_FOR_ADMINS` on (the default in production settings; the local compose stacks turn it off for the demo logins), staff and team admins must set up two-factor authentication before they can do anything else. Grant staff sparingly.
- **Team slugs**, Django admin, the background jobs (sweeper, retention, mode expiry) and the operational endpoints (`/metrics`, health probes) all span the whole deployment.

## Why not multi-tenant

Real multi-tenancy would need an `organization` on every row and a database-level guard: Postgres row-level security keyed by the current organisation, so that a forgotten filter fails closed rather than leaking. On top of that it would need per-organisation staff, per-organisation settings and quotas, and the tenant matrix rerun across organisations. That cuts across every query, and it adds nothing to what this project exists to show, which is getting the right person paged exactly once.

A deployment per organisation gets stronger isolation for free. Nothing is shared but the code: no shared database, no shared Redis, no shared secrets. The cost is operating more deployments.

## If multi-tenancy is ever needed

The work, in order:

1. Add an `Organization` model, put a non-null `organization` foreign key on `Team` and `User`, and denormalise it onto every team-owned table.
2. Turn on Postgres row-level security for those tables, with policies on `current_setting('app.organization_id')`. A middleware sets it per request, and the Celery task base sets it per task. Connect as a role that cannot bypass the policies.
3. Replace global `is_staff` with organisation admins. Keep a separate, audited path for platform operators.
4. Extend the tenant matrix to two organisations, and add a test that runs a raw SQL query without the setting and gets no rows.
5. Integration keys are already looked up by hash across the deployment, so they keep working; each key then resolves to its organisation.
