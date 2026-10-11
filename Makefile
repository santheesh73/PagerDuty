# Pulse developer commands.
#   make up       build + start the six-container stack  → http://localhost:5173
#   make check    lint + typecheck + all tests + migration drift (what CI runs)
#
# Quality targets run inside the containers by default so a fresh clone needs only Docker.
# Run them on the host instead (needs uv, Node 22, Postgres, Redis) with: make check LOCAL=1

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE ?= docker compose
ifdef LOCAL
  BACKEND  := cd backend && uv run
  FRONTEND := cd frontend &&
else
  BACKEND  := $(COMPOSE) exec -T backend
  FRONTEND := $(COMPOSE) exec -T frontend
endif

SERVICE ?= checkout-api
ROUTING_KEY ?=


.PHONY: help up down logs ps migrate seed reseed send-alert chaos-redis doctor db-backup db-restore \
        badge simulate loadtest e2e test test-backend test-frontend \
        lint typecheck format migrations-check check schema shell

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.env:
	cp .env.example .env

up: .env ## Build and start every service, then wait until the API is healthy
	$(COMPOSE) up --build -d --wait
	@echo ""
	@echo "  Pulse is up → http://localhost:5173   (API docs: http://localhost:8000/api/docs/)"

down: ## Stop the stack (keeps the database volume)
	$(COMPOSE) down

logs: ## Tail logs from every service
	$(COMPOSE) logs -f --tail=100

ps: ## Show service status
	$(COMPOSE) ps

migrate: ## Apply database migrations (also runs on every API start)
	$(BACKEND) python manage.py migrate --noinput

seed: ## Seed demo data (idempotent)
	$(BACKEND) python manage.py seed_demo

reseed: ## Wipe and re-seed demo data
	$(BACKEND) python manage.py seed_demo --reset

send-alert: ## Fire a live trigger at a seeded service (SERVICE=checkout-api)
	@set -e; key="$(ROUTING_KEY)"; \
	if [ -z "$$key" ]; then key=$$($(BACKEND) python manage.py routing_key $(SERVICE)); fi; \
	curl -sS -X POST http://localhost:8000/api/v1/events/ \
	  -H 'Content-Type: application/json' \
	  -d "{\"routing_key\":\"$$key\",\"event_action\":\"trigger\",\"dedup_key\":\"demo-$$(date +%s)\",\"payload\":{\"summary\":\"CPU above 95% on $(SERVICE)\",\"severity\":\"critical\",\"source\":\"make send-alert\"}}"; \
	echo; echo "  Open http://localhost:5173/incidents to watch it page and escalate."

chaos-redis: ## Prove a Redis wipe can't lose a page (needs `make up`)
	COMPOSE="$(COMPOSE)" ./scripts/chaos_redis.sh

doctor: ## Boot the prod-like stack from scratch and prove it works and survives failures (~8 min)
	./scripts/doctor.sh

db-backup: ## Dump the database to backups/pulse-<timestamp>.dump (custom format)
	@mkdir -p backups
	@f=backups/pulse-$$(date +%Y%m%d-%H%M%S).dump; \
	$(COMPOSE) exec -T db pg_dump -U $${POSTGRES_USER:-pulse} -Fc $${POSTGRES_DB:-pulse} > $$f && echo "wrote $$f ($$(wc -c < $$f) bytes)"

db-restore: ## Restore a dump over the database: make db-restore FILE=backups/pulse-....dump
	@test -n "$(FILE)" || { echo "usage: make db-restore FILE=backups/pulse-....dump"; exit 1; }
	$(COMPOSE) exec -T db pg_restore -U $${POSTGRES_USER:-pulse} -d $${POSTGRES_DB:-pulse} --clean --if-exists --no-owner < $(FILE)

test-backend: ## Backend tests with coverage (fails under 85%)
	$(BACKEND) pytest --cov --cov-report=term-missing:skip-covered --cov-fail-under=85

test-frontend: ## Frontend tests
	$(FRONTEND) npm test

simulate: ## Fault-injection simulator over seeds 1-20 (SEEDS=n, OPS=n to change)
	cd backend && uv run python manage.py simulate --seeds $${SEEDS:-20} --operations $${OPS:-600}

test: test-backend test-frontend ## All tests

lint: ## Ruff + ESLint + Prettier
	$(BACKEND) ruff check .
	$(BACKEND) ruff format --check .
	$(FRONTEND) npm run lint
	$(FRONTEND) npm run format:check

typecheck: ## mypy + tsc
	$(BACKEND) mypy .
	$(FRONTEND) npm run typecheck

format: ## Auto-format everything
	$(BACKEND) ruff format .
	$(BACKEND) ruff check --fix .
	$(FRONTEND) npm run format

migrations-check: ## Fail if models and migrations have drifted
	$(BACKEND) python manage.py makemigrations --check --dry-run

badge: ## Refresh docs/img/coverage.svg from the last backend test run (LOCAL)
	cd backend && uv run pytest -q --cov >/dev/null && cd .. && python3 scripts/coverage_badge.py

schema: ## Regenerate OpenAPI schema and the frontend's TS types
	$(BACKEND) python manage.py spectacular --file openapi.yaml --validate
	$(FRONTEND) npm run gen:api

loadtest: ## k6 against the prod-like stack (VUS=32 DURATION=60s); then verify the database
	@set -e; export SECRET_KEY=$${SECRET_KEY:-loadtest} THROTTLE_EVENTS=$${THROTTLE_EVENTS:-100000/min} SEED_DEMO=1; \
	dc="$${COMPOSE:-docker compose -f docker-compose.prod.yml}"; $$dc up --build -d --wait --wait-timeout 300; \
	key=$$($$dc exec -T api python manage.py routing_key checkout-api | tail -1); run=load$$$$; \
	mkdir -p loadtest/out; chmod 777 loadtest/out; \
	docker run --rm --network host -v "$$PWD/loadtest:/loadtest" -v "$$PWD/loadtest/out:/out" grafana/k6:2.3.0 run --quiet \
	  -e BASE_URL=http://localhost:8080 -e ROUTING_KEY=$$key -e RUN_ID=$$run \
	  -e VUS=$${VUS:-32} -e DURATION=$${DURATION:-60s} /loadtest/events.js; \
	new=$$(python3 -c "import json;print(json.load(open('loadtest/out/summary.json'))['metrics']['pulse_new_keys']['values']['count'])"); \
	hot=$$(python3 -c "import json;print(json.load(open('loadtest/out/summary.json'))['metrics']['pulse_hot_requests']['values']['count'])"); \
	$$dc exec -T api python - --run-id $$run --new-keys $$new --hot-requests $$hot < loadtest/verify.py

e2e: ## One Playwright journey against the prod-like stack (needs `docker compose -f docker-compose.prod.yml up -d`)
	cd e2e && npm ci && npx playwright install chromium && npx playwright test

check: lint typecheck migrations-check test ## Everything CI runs

shell: ## Django shell
	$(BACKEND) python manage.py shell
