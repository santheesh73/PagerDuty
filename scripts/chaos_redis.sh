#!/usr/bin/env bash
# Chaos check for Pulse's headline claim: losing Redis never loses a page.
#
#   1. Trigger a critical alert (level 1 escalates after 1 minute) and show the ETA message
#      is sitting in Redis.
#   2. Restart Redis (no persistence: every queued message, the ETA escalation task included,
#      is gone) and the workers (they drop anything prefetched). Prove the queue really is empty.
#   3. Wait. The Beat sweeper reads `next_escalation_at` from Postgres and escalates anyway.
#   4. Assert the outcome in the database, not just "a level went up":
#        - exactly one incident exists for the alert's dedup key
#        - it escalated exactly once, to level 2
#        - every page owed (both levels, both channels) exists once and none is still pending
#
# Usage: make chaos-redis      (needs the stack from `make up` and the demo data)
#        COMPOSE="docker compose -f docker-compose.prod.yml" API_SERVICE=api \
#          API=http://localhost:8080 WORKERS="worker worker-escalations" ./scripts/chaos_redis.sh
set -euo pipefail

COMPOSE=${COMPOSE:-docker compose}
API=${API:-http://localhost:8000}
API_SERVICE=${API_SERVICE:-backend}
WORKERS=${WORKERS:-worker worker-escalations}
SERVICE=${SERVICE:-checkout-api}

fail() { echo "FAIL: $*" >&2; exit 1; }
dj() { $COMPOSE exec -T "$API_SERVICE" python manage.py shell -v0 -c "$1"; }

key=$($COMPOSE exec -T "$API_SERVICE" python manage.py routing_key "$SERVICE" | tail -1)
dedup="chaos-$(date +%s)"
incident=$(curl -sS -X POST "$API/api/v1/events/" -H 'Content-Type: application/json' -d \
  "{\"routing_key\":\"$key\",\"event_action\":\"trigger\",\"dedup_key\":\"$dedup\",\"payload\":{\"summary\":\"Chaos test: Redis is about to disappear\",\"severity\":\"critical\",\"source\":\"chaos_redis.sh\"}}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["incident_id"])')
echo "Triggered incident $incident (escalation due in 1 minute)."

queued=$($COMPOSE exec -T redis redis-cli llen escalations | tr -d '\r')
echo "Escalation messages queued in Redis before the wipe: $queued"

echo "Restarting Redis and the workers: the ETA escalation message is now gone."
# shellcheck disable=SC2086
$COMPOSE restart redis $WORKERS >/dev/null
sleep 3
after=$($COMPOSE exec -T redis redis-cli llen escalations | tr -d '\r')
[ "$after" = "0" ] || fail "expected an empty escalations queue after the restart, found $after message(s): Redis was not actually wiped"
echo "Escalations queue after the restart: 0 (the message really was lost)."

check='
import json
from django.db.models import Count
from apps.incidents.models import Incident, IncidentEvent
from apps.notifications.models import Notification
inc = Incident.objects.get(pk=%s)
same_key = Incident.objects.filter(service=inc.service, dedup_key=inc.dedup_key).exclude(status="resolved").count()
rows = Notification.objects.filter(incident=inc)
dupes = rows.values("user", "channel", "idempotency_key").annotate(n=Count("pk")).filter(n__gt=1).count()
print(json.dumps({
  "level": inc.escalation_level,
  "open_incidents_for_key": same_key,
  "escalations": IncidentEvent.objects.filter(incident=inc, type="escalated").count(),
  "rows": rows.count(),
  "pending": rows.filter(status="pending").count(),
  "failed": rows.filter(status="failed").count(),
  "sent": rows.filter(status="sent").count(),
  "duplicate_rows": dupes,
  "levels_paged": sorted({k.split(":level:")[1].split(":")[0] for k in rows.values_list("idempotency_key", flat=True)}),
}))'

state=""
for i in $(seq 1 "${CHAOS_ATTEMPTS:-60}"); do   # 5 s each: escalation ~1 min, lost deliveries re-driven within ~2.5 min
  sleep 5
  # shellcheck disable=SC2059
  state=$(dj "$(printf "$check" "$incident")" | tail -1)
  ok=$(python3 - "$state" <<'PY'
import json, sys
s = json.loads(sys.argv[1])
print("yes" if s["level"] >= 1 and s["pending"] == 0 and s["rows"] >= 4 else "no")
PY
)
  [ "$ok" = "yes" ] && break
done
echo "Final state: $state"

python3 - "$state" <<'PY' || exit 1
import json, sys
s = json.loads(sys.argv[1])
problems = []
if s["open_incidents_for_key"] != 1:
    problems.append(f"{s['open_incidents_for_key']} open incidents for the alert's key (want exactly 1)")
if s["level"] != 1:
    problems.append(f"escalation level is {s['level']} (want 1, i.e. level 2 of the policy)")
if s["escalations"] != 1:
    problems.append(f"{s['escalations']} escalated events (want exactly 1)")
if s["levels_paged"] != ["0", "1"]:
    problems.append(f"pages exist for levels {s['levels_paged']} (want ['0', '1'])")
if s["pending"] != 0:
    problems.append(f"{s['pending']} notification(s) still pending: a page was lost")
if s["failed"] != 0:
    problems.append(f"{s['failed']} notification(s) failed")
if s["duplicate_rows"] != 0:
    problems.append(f"{s['duplicate_rows']} duplicated notification rows")
if s["rows"] < 4 or s["sent"] != s["rows"]:
    problems.append(f"{s['sent']} of {s['rows']} notifications sent (want all, at least 4)")
if problems:
    print("FAIL:", "; ".join(problems), file=sys.stderr)
    sys.exit(1)
print(f"PASS: after losing Redis, incident escalated once to level 2 from Postgres, "
      f"{s['sent']} pages sent exactly once, none pending.")
PY
