#!/usr/bin/env bash
# Chaos check for Pulse's headline claim: losing Redis never loses a page.
#
# 1. Trigger a critical alert (escalation due in 1 minute).
# 2. Restart Redis (no persistence: every queued message, including the ETA escalation
#    task, is gone) and the worker (drops anything it had prefetched).
# 3. Wait. The Beat sweeper reads `next_escalation_at` from Postgres and escalates anyway.
#
# Usage: make chaos-redis   (needs the stack from `make up` and seeded demo data)
set -euo pipefail

COMPOSE=${COMPOSE:-docker compose}
API=${API:-http://localhost:8000}
SERVICE=${SERVICE:-checkout-api}

key=$($COMPOSE exec -T backend python manage.py routing_key "$SERVICE")
dedup="chaos-$(date +%s)"
incident=$(curl -sS -X POST "$API/api/v1/events/" -H 'Content-Type: application/json' -d \
  "{\"routing_key\":\"$key\",\"event_action\":\"trigger\",\"dedup_key\":\"$dedup\",\"payload\":{\"summary\":\"Chaos test: Redis is about to disappear\",\"severity\":\"critical\",\"source\":\"chaos_redis.sh\"}}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["incident_id"])')
echo "Triggered incident $incident (escalation due in 1 minute)."

echo "Wiping Redis and restarting the worker: the ETA escalation message is now gone."
$COMPOSE restart redis worker >/dev/null

level() {
  $COMPOSE exec -T backend python manage.py shell -v0 -c \
    "from apps.incidents.models import Incident; i=Incident.objects.get(pk=$incident); print(i.escalation_level)"
}

for i in $(seq 1 24); do
  sleep 5
  if [ "$(level)" -ge 1 ]; then
    echo "PASS: incident $incident escalated to level 2 after ~$((i * 5))s, recovered by the Beat sweeper from Postgres."
    exit 0
  fi
done
echo "FAIL: incident $incident never escalated." >&2
exit 1
