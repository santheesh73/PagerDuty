# Stack and pinned versions

Every version was checked against PyPI / npm on **2026-10-10** and pinned exactly.
Lockfiles: `backend/uv.lock`, `frontend/package-lock.json`.

## Runtime and infrastructure

Production images: `python:3.13-slim` + uv 0.11.32 (API, worker, beat, cron) and `nginx:1.29-alpine` serving the built SPA.

| Component | Version | Why |
|---|---|---|
| Python | 3.13 | Newest interpreter that Celery 5.6 officially supports. |
| PostgreSQL | 17 (`postgres:17-alpine`) | Partial unique indexes and `SKIP LOCKED` are the backbone of dedup and the escalation sweeper. |
| Redis | 7.4 (`redis:7.4-alpine`) | Broker and cache only, deliberately run without persistence. |
| Node | 22.22 LTS | Active LTS; React Router 7 / Vite 8 require ≥ 22.12. |

## Backend (`backend/pyproject.toml`)

| Package | Version | Why |
|---|---|---|
| Django | 6.0.9 | Newest release line that *every* dependency below declares support for (6.1 is out, but drf-spectacular and django-cors-headers only declare support up to 6.0). |
| djangorestframework | 3.18.3 | Latest; declares Django 6.0 support. |
| drf-spectacular | 0.30.0 | OpenAPI 3 schema that drives the generated TypeScript types. |
| django-filter | 26.2 | Declarative query-param filters for the incident list. |
| django-cors-headers | 4.9.0 | Only needed when the SPA is deployed on a different origin. |
| celery[redis] | 5.6.3 | Workers, ETA tasks and Beat. Ships kombu 5.6, which caps `redis-py` at 6.4 — hence no separate `redis` pin. |
| psycopg[binary] | 3.3.6 | psycopg 3: the maintained driver, required by Django 6. |
| dj-database-url | 3.1.2 | One `DATABASE_URL` for every environment. |
| gunicorn | 26.2.0 | Production WSGI server. |
| whitenoise | 6.12.0 | Serves admin/static assets from the app container without nginx. |
| python-json-logger | 4.2.0 | Structured JSON logs with request IDs. |

### Dev / test

| Package | Version | Why |
|---|---|---|
| pytest | 9.1.1 | Test runner. |
| pytest-django | 4.14.0 | DB fixtures, `transaction=True` for the concurrency tests. |
| pytest-cov | 7.1.0 | Coverage gate on the engine modules. |
| factory-boy | 3.3.3 | One-call object graphs for every model. |
| time-machine | 3.5.1 | Frozen / travelled time for escalation and DST tests (faster and more precise than freezegun). |
| ruff | 0.17.0 | Lint + format in one tool. |
| mypy | 2.3.1 | Highest version `django-stubs[compatible-mypy]` 6.0.9 allows (mypy 2.4 is out but not yet supported by the plugin). |
| django-stubs | 6.0.9 | Matches the Django minor version. |
| djangorestframework-stubs | 3.16.9 | Latest stubs compatible with django-stubs 6.0. |
| celery-types | 0.26.0 | Type stubs for Celery. |

## Frontend (`frontend/package.json`)

| Package | Version | Why |
|---|---|---|
| react / react-dom | 19.3.0 | Latest stable. |
| typescript | 5.9.3 | TypeScript 7 (native compiler) is out, but `typescript-eslint` caps at `<6.1` and `openapi-typescript` peers on `^5`. |
| vite | 8.3.4 | Latest; dev server proxy keeps the SPA same-origin with Django. |
| @vitejs/plugin-react | 6.1.2 | Matches Vite 8. |
| react-router | 7.18.4 | v7 is the floor; v8 is out, but v7 is the mature line with a stable data-router API and no migration risk. |
| @tanstack/react-query | 5.104.1 | Server-state cache, polling and optimistic mutations. |
| tailwindcss / @tailwindcss/vite | 4.3.3 | Design tokens as CSS variables; dark mode without a component kit's default look. |
| recharts | 3.10.1 | Analytics charts. |
| lucide-react | 1.55.0 | Icon set. |
| sonner | 2.0.8 | Toasts. |
| clsx | 2.1.1 | Conditional class names. |
| tailwind-merge | 3.7.0 | Lets a caller's `w-36` override a component's default `w-full` predictably. |
| openapi-typescript | 7.13.0 | Generates `src/api/schema.d.ts` from the backend's OpenAPI schema. |
| vitest / @vitest/coverage-v8 | 5.0.3 | Test runner sharing Vite's config. |
| @testing-library/react | 16.3.3 | Component tests through the user's eyes. |
| @testing-library/user-event | 14.6.7 | Realistic interactions. |
| @testing-library/jest-dom | 7.0.1 | DOM matchers. |
| jsdom | 30.1.2 | Test DOM. |
| eslint / @eslint/js | 10.12.0 / 10.0.1 | Flat config. |
| typescript-eslint | 8.71.1 | Type-aware lint rules. |
| eslint-plugin-react-hooks | 7.1.1 | Rules of hooks. |
| prettier | 3.9.10 | Formatting. |
