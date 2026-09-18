# Incident Management Platform

A deterministic, production-grade incident management platform providing automated alert ingestion, deduplication, on-call scheduling, tiered escalation policies, notification delivery, and incident lifecycle tracking.

---

## 1. Project Overview

The Incident Management Platform coordinates emergency response workflows during production incidents. It handles alert triage, dedupes recurring alerts against active incidents, identifies service escalation policies and on-call responders, triggers automated notifications, and manages incident escalation and resolution states with auditable event histories.

---

## 2. Architecture

```
React 18 + TypeScript + Vite
        │
        │ REST / JSON
        ▼
Django 5.x + Django REST Framework
        │
        ├──────────────────────► PostgreSQL 15+
        │
        ▼
Redis 7.x
        │
        ▼
Celery 5.x workers
        │
        └──────────────────────► PostgreSQL
```

### Component Responsibilities:
- **Django**: Owns the domain model, business rules, REST APIs, payload validation, and workflow orchestration.
- **PostgreSQL**: Single source of truth storing all users, services, alerts, incidents, schedules, escalation policies, notifications, and event history.
- **Redis**: In-memory broker for Celery task queues.
- **Celery**: Asynchronous worker execution for escalation timers, retries, notification dispatch, and scheduled checks.
- **React**: Thin REST client statefully rendered via TanStack Query; contains no server domain or business logic.

---

## 3. Technology Stack

- **Backend**: Python 3.11, Django 5.1+, Django REST Framework 3.15+, Celery 5.4+, Psycopg 3.3+, Ruff
- **Database & Broker**: PostgreSQL 16+, Redis 7+
- **Frontend**: React 18, TypeScript 5, Vite 5, Tailwind CSS 3, TanStack React Query 5, Vitest
- **Containerization**: Docker, Docker Compose

---

## 4. Repository Structure

```
incident-platform/
├── README.md                 # System overview and developer instructions
├── docker-compose.yml        # Development stack definition (Postgres, Redis, Backend, Celery, Frontend)
├── .env.example              # Environment variable baseline template
├── .gitignore                # Git exclusions
├── skills/                   # Repository skills and workflows
├── transcripts/              # Authentic session records and logs
├── e2e/                      # End-to-End test suite foundation
│
├── backend/
│   ├── manage.py             # Django administrative entrypoint
│   ├── pyproject.toml        # Backend configuration and dependency definitions
│   ├── requirements.txt      # Production dependencies
│   ├── requirements-dev.txt  # Development and test dependencies
│   ├── Dockerfile            # Backend container definition
│   ├── pytest.ini            # Pytest configuration
│   ├── config/               # Project configuration & settings
│   │   ├── __init__.py       # Celery app export
│   │   ├── celery.py         # Celery configuration and smoke tasks
│   │   ├── urls.py           # Root routing & /api/health/ endpoint
│   │   ├── wsgi.py           # WSGI entrypoint
│   │   ├── asgi.py           # ASGI entrypoint
│   │   └── settings/         # Split settings modules
│   │       ├── __init__.py
│   │       ├── base.py       # Shared settings
│   │       ├── dev.py        # Development settings
│   │       └── prod.py       # Production hardened settings
│   ├── apps/                 # Domain applications
│   │   ├── users/            # Users, Teams, TeamMembership
│   │   ├── services/         # Services
│   │   ├── alerts/           # Alerts & triage pipeline
│   │   ├── incidents/        # Incidents & state machines
│   │   ├── scheduling/       # On-call schedules & rotations
│   │   ├── escalation/       # Escalation policies & levels
│   │   ├── notifications/    # Notifications & dispatch
│   │   └── analytics/        # MTTA / MTTR metrics
│   ├── fixtures/             # Data fixtures
│   └── tests/                # Infrastructure & integration test suite
│
└── frontend/
    ├── package.json          # Node dependencies & scripts
    ├── vite.config.ts        # Vite configuration
    ├── vitest.config.ts      # Vitest test runner configuration
    ├── tailwind.config.js    # Tailwind CSS configuration
    ├── tsconfig.json         # TypeScript configuration
    ├── Dockerfile            # Frontend container definition
    └── src/
        ├── main.tsx          # Application entrypoint
        ├── App.tsx           # QueryClientProvider and root component
        ├── api/              # Typed API client & endpoints
        ├── hooks/            # TanStack Query custom hooks
        ├── types/            # TypeScript type declarations
        ├── components/       # Shared UI components
        └── pages/            # View components & status dashboard
```

---

## 5. Environment Variables

Copy the template to initialize your local environment:

```bash
cp .env.example .env
```

| Variable | Description | Default / Example |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | Active Django settings module | `config.settings.dev` |
| `DJANGO_SECRET_KEY` | Application cryptographic secret | *Random secret string* |
| `DJANGO_DEBUG` | Debug mode toggle | `True` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed hostnames | `localhost,127.0.0.1,backend,web` |
| `POSTGRES_DB` | PostgreSQL database name | `incident_platform` |
| `POSTGRES_USER` | PostgreSQL user | `postgres` |
| `POSTGRES_PASSWORD` | PostgreSQL password | `postgres` |
| `POSTGRES_HOST` | PostgreSQL host | `localhost` or `postgres` |
| `POSTGRES_PORT` | PostgreSQL port | `5432` |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `CELERY_BROKER_URL` | Celery broker URL | `redis://localhost:6379/0` |
| `CELERY_RESULT_BACKEND` | Celery result backend URL | `redis://localhost:6379/1` |
| `VITE_API_BASE_URL` | Frontend REST API base URL | `http://localhost:8000/api` |

---

## 6. Local Development

### Prerequisites
- Python 3.11+
- Node.js 20+
- PostgreSQL 16+ & Redis 7+ (or run via Docker)

### Backend Setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Or on Windows: .\.venv\Scripts\activate
pip install -r requirements-dev.txt

python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

The frontend will be accessible at `http://localhost:5173`.

---

## 7. Docker Development Stack

Start the entire environment using Docker Compose:

```bash
docker compose up --build
```

To run detached in background:
```bash
docker compose up -d --build
```

### Services Started:
- **PostgreSQL**: `localhost:5432` (Health-monitored)
- **Redis**: `localhost:6379` (Health-monitored)
- **Django REST API**: `http://localhost:8000`
- **Celery Worker**: Asynchronous background worker
- **React Frontend**: `http://localhost:5173`

Verify infrastructure health:
```bash
curl http://localhost:8000/api/health/
```

---

## 8. Running Backend Tests

```bash
cd backend
# Run test suite
pytest

# Run Django system checks
python manage.py check

# Run Ruff linter
ruff check .
```

---

## 9. Running Frontend Tests

```bash
cd frontend
# Run Vitest test suite
npm test

# Run TypeScript typecheck
npm run typecheck

# Run ESLint
npm run lint

# Run production build check
npm run build
```

---

## 10. Current Implementation Status

### Current Implementation:
**Phase 0 — Skeleton (Complete)**
- Full repository structure and separation of concerns established.
- Django 5.x booted with PostgreSQL and Redis configurations.
- Celery worker initialized with task auto-discovery and smoke task (`health_ping`).
- React 18 + TypeScript + Vite + Tailwind configured with TanStack Query.
- Health endpoint (`GET /api/health/`) operational and bound to frontend status UI.
- Automated tests, linting, typechecking, and Docker Compose stack validated.

### Not Yet Implemented:
- users/teams functionality
- service management
- alert ingestion
- incident lifecycle
- scheduling
- escalation
- notifications
- analytics
- operational frontend
