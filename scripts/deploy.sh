#!/usr/bin/env bash
# Deploy a release of Pulse to this Docker host, prove it with smoke.sh, and roll back if it fails.
#
#   ./scripts/deploy.sh [git-ref]     build and deploy a ref (default: origin/main)
#   ./scripts/deploy.sh --rollback    go back to the previous release
#   ./scripts/deploy.sh --status      which release is live, and which is the rollback target
#
# Reads .env.production (copy deploy/.env.production.example). Images are tagged with the
# release's git SHA, so a rollback is a restart on images already on the host: no rebuild, no
# registry. Migrations are never reversed. They must be expand-only (make lint-migrations
# enforces it), so the previous release keeps working against the new schema.
# Needs Docker Compose 2.24+, git, curl. docs/DEPLOY.md has the whole procedure.
set -euo pipefail
cd "$(dirname "$0")/.."

# Everything runs inside main(), which bash parses in full before running: the checkout below
# replaces this very file with the release's version.
main() {
  ENV_FILE=${ENV_FILE:-.env.production}
  STATE=${STATE_DIR:-.deploy}
  [ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE (copy deploy/.env.production.example)"; exit 1; }
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
  : "${DOMAIN:?DOMAIN must be set in $ENV_FILE}"
  COMPOSE=(docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml -f deploy/compose.production.yml)
  mkdir -p "$STATE"
  current=$(cat "$STATE/current" 2>/dev/null || true)
  previous=$(cat "$STATE/previous" 2>/dev/null || true)

  start() {  # start <tag> [extra compose up args]: run that release and wait until it is healthy
    local tag=$1
    shift
    PULSE_TAG=$tag GIT_SHA=$tag "${COMPOSE[@]}" up -d --wait --wait-timeout 300 --remove-orphans "$@"
  }

  smoke() { ./scripts/smoke.sh "https://$DOMAIN"; }

  case "${1:-}" in
    --status)
      echo "live: ${current:-none}   rollback target: ${previous:-none}"
      exit 0
      ;;
    --rollback)
      [ -n "$previous" ] || { echo "no previous release recorded in $STATE/"; exit 1; }
      echo "rolling back ${current:-?} -> $previous (schema stays as it is: migrations are expand-only)"
      start "$previous" --no-build
      echo "$previous" >"$STATE/current"
      echo "${current}" >"$STATE/previous"
      smoke
      exit
      ;;
  esac

  ref=${1:-origin/main}
  git fetch --quiet origin
  tag=$(git rev-parse --short=12 "$ref^{commit}")
  if [ "$tag" = "$current" ]; then
    echo "$tag is already live"
    exit 0
  fi
  git -c advice.detachedHead=false checkout --quiet "$tag"
  echo "deploying $tag (live: ${current:-none})"

  PULSE_TAG=$tag GIT_SHA=$tag "${COMPOSE[@]}" build
  # Migrate once, before any new process serves traffic. The running release keeps serving
  # meanwhile, which is safe only because migrations are expand-only.
  PULSE_TAG=$tag "${COMPOSE[@]}" run --rm -e DB_STATEMENT_TIMEOUT_MS=0 api \
    python manage.py migrate_safely
  start "$tag"

  if smoke; then
    if [ -n "$current" ]; then echo "$current" >"$STATE/previous"; fi
    echo "$tag" >"$STATE/current"
    echo "deployed $tag; rollback target: ${current:-none}"
  else
    echo "smoke test failed on $tag"
    if [ -n "$current" ]; then
      echo "rolling back to $current"
      start "$current" --no-build
      git -c advice.detachedHead=false checkout --quiet "$current"
      smoke || echo "WARNING: the rollback also fails its smoke test; investigate now"
    fi
    exit 1
  fi
}

main "$@"
