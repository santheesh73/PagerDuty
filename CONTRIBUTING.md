# Contributing

## Set up

Docker is enough: `cp .env.example .env && make up`, then open <http://localhost:5173>. The README has a no-Docker path.

## Before you open a pull request

```bash
make check     # ruff, mypy, eslint, prettier, tsc, migration drift, backend + frontend tests
make audit     # pip-audit, npm audit, Trivy (lockfiles, Dockerfiles, secrets)
```

CI runs all of that, plus the migration linter, the OpenAPI diff, the bundle budget, Docker image scans, the browser journey, the load smoke, `make doctor` and the backup drill.

## House rules

- **A bug fix comes with a test that fails without it.** Check this by reverting the fix once. Name tests after the behaviour (`test_ack_stops_escalation`), not after the function.
- **Guarantees live in [docs/INVARIANTS.md](docs/INVARIANTS.md).** If a change touches paging, escalation, scheduling or tenancy, check which invariant it affects and keep that entry's mechanism and proof accurate.
- **Migrations must be safe on a live database.** `make lint-migrations` flags table rewrites, non-concurrent indexes and dropped defaults. Expand first, contract in a later release.
- **The API contract is committed.** After changing a serializer or endpoint, run `make schema` and commit `backend/openapi.yaml` together with the regenerated frontend types. The conventions are in [docs/API.md](docs/API.md).
- **No secrets in git, ever.** Configuration comes from environment variables, and every external service is off by default. Tests use fakes, never real third-party APIs.
- **New dependencies need a one-line justification** in the pull request. Dependabot keeps existing ones current.
- **Style is enforced by the tools** (ruff, eslint, prettier); don't hand-format. Keep comments for the *why*.

## Commits and pull requests

Keep commits small, with an imperative subject line ("Validate list filters"). Fill in the pull request template. Anything security-sensitive goes through [SECURITY.md](SECURITY.md), not a public issue.
