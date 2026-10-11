#!/usr/bin/env bash
# Boot the production-like stack from scratch, prove it works and survives failures, tear down.
#   make doctor                 (or ./scripts/doctor.sh)
#   make doctor-demo            (DOCTOR_MODE=demo: the one-container demo, no Redis or Celery)
# Env: KEEP=1 leaves the stack running; SKIP_DRILLS=1 skips the failure drills;
#      DOCTOR_COMPOSE overrides the compose command (e.g. to add an override file).
# Needs Docker, ports 8080 and 8025 free, and python3 on the host (stdlib only).
set -euo pipefail
cd "$(dirname "$0")/.."

MODE=${DOCTOR_MODE:-full}
export SECRET_KEY=${SECRET_KEY:-doctor-not-a-secret}
export SEED_DEMO=1 SHOW_DEMO_CREDENTIALS=true
if [ "$MODE" = "demo" ]; then
  COMPOSE=${DOCTOR_COMPOSE:-"docker compose -p pulse-doctor-demo -f docker-compose.demo.yml"}
  export TICK_SECRET=${TICK_SECRET:-doctor-tick-not-a-secret}
  args=(--demo --tick-secret "$TICK_SECRET" --api-service app)
else
  COMPOSE=${DOCTOR_COMPOSE:-"docker compose -p pulse-doctor -f docker-compose.prod.yml"}
  args=(--api-service api)
fi
LOGS=${DOCTOR_LOGS:-doctor-logs.txt}
status=1

# shellcheck disable=SC2317,SC2329  # called by the EXIT trap, which shellcheck cannot see
cleanup() {
  if [ "$status" -ne 0 ]; then
    echo "doctor failed: saving logs to $LOGS"
    $COMPOSE ps -a >"$LOGS" 2>&1 || true
    $COMPOSE logs --no-color --tail 300 >>"$LOGS" 2>&1 || true
  fi
  if [ "${KEEP:-0}" != "1" ]; then $COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT

$COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true
$COMPOSE up --build -d --wait --wait-timeout 300
$COMPOSE ps

args+=(--compose "$COMPOSE" --base http://localhost:8080 --mail http://localhost:8025)
if [ "${SKIP_DRILLS:-0}" = "1" ]; then args+=(--skip-drills); fi
python3 scripts/doctor.py "${args[@]}" && status=0 || status=$?
exit "$status"
