## What and why

<!-- The problem, and how this change solves it. Link the issue if there is one. -->

## How it was verified

<!-- Commands you ran and what they printed. For a bug fix: the test that fails without the fix. -->

## Checklist

- [ ] `make check` passes
- [ ] A bug fix has a regression test that fails without the fix
- [ ] Affected guarantees in `docs/INVARIANTS.md` and other docs are still accurate
- [ ] Migrations pass `make lint-migrations`; API changes are in `backend/openapi.yaml` (`make schema`)
- [ ] No secrets, tokens or real customer data in the diff
- [ ] Any new dependency is justified above
