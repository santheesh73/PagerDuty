#!/usr/bin/env bash
# Prove the backups work: seed a database, back it up, restore into a scratch database, compare
# it with the original, and boot the API against the restored copy.
#
#   DATABASE_URL=postgres://user:pass@host:5432/anydb scripts/backup_drill.sh     (make backup-drill)
#
# DATABASE_URL only locates the Postgres server and a role allowed to CREATE DATABASE; two
# throwaway databases are created and dropped. Needs pg_dump/pg_restore/psql (same major version
# as the server), the backend's Python environment and curl. Redis is optional (readyz may say
# "degraded", which still serves).
#
# Compared after restore: row count of every table, every index definition, every constraint
# definition, and every sequence value (a wrong sequence would hand out a duplicate incident
# number). Then the restored copy must serve a login, list the same incidents, and accept a new
# alert (which exercises the dedup index and sequences).
set -euo pipefail

: "${DATABASE_URL:?set DATABASE_URL}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-uv run python}"
SUFFIX="$$"
SRC="pulse_drill_src_$SUFFIX"
DST="pulse_drill_restored_$SUFFIX"
WORK="$(mktemp -d)"
PORT="${DRILL_PORT:-18765}"
API_PID=""

swap_db() { printf '%s' "$DATABASE_URL" | sed -E "s#/[^/?]*(\\?.*)?\$#/$1\\1#"; }
ADMIN_URL="$(swap_db postgres)"
SRC_URL="$(swap_db "$SRC")"
DST_URL="$(swap_db "$DST")"

cleanup() {
  if [ -n "$API_PID" ]; then kill "$API_PID" 2>/dev/null || true; wait "$API_PID" 2>/dev/null || true; fi
  psql "$ADMIN_URL" -qAt -c "DROP DATABASE IF EXISTS \"$SRC\" WITH (FORCE)" >/dev/null 2>&1 || true
  psql "$ADMIN_URL" -qAt -c "DROP DATABASE IF EXISTS \"$DST\" WITH (FORCE)" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

fail() { echo "DRILL FAIL: $*" >&2; [ -f "$WORK/api.log" ] && tail -15 "$WORK/api.log" >&2; exit 1; }
ok() { echo "  ok  $*"; }
manage() { (cd "$ROOT/backend" && DJANGO_SETTINGS_MODULE=config.settings.dev DB_STATEMENT_TIMEOUT_MS=0 $PY manage.py "$@"); }

echo "== 1. seed a source database"
psql "$ADMIN_URL" -qAt -c "CREATE DATABASE \"$SRC\"" >/dev/null
DATABASE_URL="$SRC_URL" manage migrate_safely -v 0
DATABASE_URL="$SRC_URL" manage seed_demo >/dev/null
tables="$(psql "$SRC_URL" -qAt -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")"
incidents="$(psql "$SRC_URL" -qAt -c "SELECT count(*) FROM incidents_incident")"
[ "$incidents" -gt 0 ] || fail "seed produced no incidents"
ok "$tables tables, $incidents incidents"

echo "== 2. back up"
t0=$(date +%s)
DATABASE_URL="$SRC_URL" BACKUP_DIR="$WORK/backups" "$ROOT/scripts/backup.sh" | tail -1
dump="$(ls -1 "$WORK"/backups/daily/pulse-*.dump | head -1)"
t1=$(date +%s)

echo "== 3. restore into a scratch database"
psql "$ADMIN_URL" -qAt -c "CREATE DATABASE \"$DST\"" >/dev/null
"$ROOT/scripts/restore.sh" "$dump" "$DST_URL" >/dev/null
t2=$(date +%s)
ok "backup took $((t1 - t0))s, restore took $((t2 - t1))s"

echo "== 4. compare the restored database with the original"
q() { psql "$1" -qAt -c "$2"; }
counts() {
  for t in $(q "$1" "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1"); do
    echo "$t $(q "$1" "SELECT count(*) FROM \"$t\"")"
  done
}
diff <(counts "$SRC_URL") <(counts "$DST_URL") >/dev/null || fail "row counts differ"
ok "row counts identical in every table"
idx="SELECT indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY 1"
diff <(q "$SRC_URL" "$idx") <(q "$DST_URL" "$idx") >/dev/null || fail "index definitions differ"
ok "$(q "$DST_URL" "SELECT count(*) FROM pg_indexes WHERE schemaname='public'") index definitions identical"
con="SELECT conrelid::regclass, conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE connamespace='public'::regnamespace ORDER BY conrelid::regclass::text, conname"
diff <(q "$SRC_URL" "$con") <(q "$DST_URL" "$con") >/dev/null || fail "constraint definitions differ"
ok "$(q "$DST_URL" "SELECT count(*) FROM pg_constraint WHERE connamespace='public'::regnamespace") constraints identical"
q "$DST_URL" "SELECT 1 FROM pg_indexes WHERE indexname='uniq_open_incident_per_dedup_key'" | grep -q 1 \
  || fail "dedup unique index missing after restore"
ok "partial unique index uniq_open_incident_per_dedup_key restored"
seq="SELECT sequencename, last_value FROM pg_sequences WHERE schemaname='public' ORDER BY 1"
diff <(q "$SRC_URL" "$seq") <(q "$DST_URL" "$seq") >/dev/null || fail "sequence values differ"
ok "sequences identical"

echo "== 5. boot the API against the restored database"
key="$(DATABASE_URL="$DST_URL" manage routing_key checkout-api | tail -1)"
# exec the interpreter itself (not `uv run`) so $API_PID is the gunicorn master we can kill;
# a stale server left on the port would answer for a database that no longer exists.
if curl -s -o /dev/null "http://127.0.0.1:$PORT/healthz"; then fail "port $PORT is already in use"; fi
PYBIN="$(cd "$ROOT/backend" && $PY -c 'import sys; print(sys.executable)' | tail -1)"
(cd "$ROOT/backend" && DATABASE_URL="$DST_URL" DJANGO_SETTINGS_MODULE=config.settings.dev \
  SECRET_KEY=drill-only exec "$PYBIN" -m gunicorn config.wsgi:application \
  --bind "127.0.0.1:$PORT" --workers 2 >"$WORK/api.log" 2>&1) &
API_PID=$!
for _ in $(seq 1 60); do
  curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1 && break
  sleep 0.5
done
code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/readyz")"
[ "$code" = "200" ] || fail "/readyz answered $code"
ok "/readyz 200"

python3 - "$PORT" "$key" "$incidents" "$SUFFIX" <<'PY' || fail "API checks against the restored database failed"
import http.cookiejar, json, sys, urllib.request

port, key, expected, suffix = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
base = f"http://127.0.0.1:{port}"
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def call(path, body=None, headers=None):
    request = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Referer": base + "/", **(headers or {})},
    )
    with opener.open(request, timeout=30) as response:
        return response.status, json.load(response) if response.length != 0 else None


call("/api/v1/auth/csrf/")
csrf = next(c.value for c in jar if c.name == "csrftoken")
call("/api/v1/auth/login/", {"email": "admin@demo.local", "password": "demo1234"},
     {"X-CSRFToken": csrf})
print("  ok  demo admin can log in")

seen, path = 0, "/api/v1/incidents/?page_size=100"
while path:
    _, page = call(path)
    seen += len(page["results"])
    nxt = page.get("next")
    path = nxt.replace(base, "") if nxt else None
if seen != expected:
    sys.exit(f"API lists {seen} incidents, the source had {expected}")
print(f"  ok  API lists all {seen} incidents")

status, body = call("/api/v1/events/", {
    "routing_key": key, "event_action": "trigger", "dedup_key": f"drill-{suffix}",
    "payload": {"summary": "restore drill", "severity": "critical", "source": "backup_drill"},
})
if status != 202 or body["status"] != "accepted":
    sys.exit(f"new alert answered {status}: {body}")
print("  ok  a new alert is accepted and opens an incident")
PY

echo
echo "DRILL PASS  (dump $(wc -c < "$dump") bytes; backup $((t1 - t0))s, restore $((t2 - t1))s)"
