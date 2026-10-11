#!/usr/bin/env bash
# Post-deploy smoke test against a running Pulse, from the outside. Read-only unless asked.
#
#   ./scripts/smoke.sh https://pulse.example.com
#
# Optional:
#   SMOKE_EMAIL / SMOKE_PASSWORD   also sign in and read /api/v1/me/ (an account without MFA)
#   TICK_SECRET                    also call POST /internal/tick/ (demo mode)
#   EXPECT_DEMO=1                  require demo mode (readiness reports no Redis)
#
# Exits non-zero if any check fails; scripts/deploy.sh rolls back on that. Needs curl only.
set -uo pipefail

BASE=${1:?usage: smoke.sh <base-url>}
BASE=${BASE%/}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
JAR="$TMP/cookies"
failures=0

pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s  (%s)\n' "$1" "$2"; failures=$((failures + 1)); }

# fetch <name> <method> <path> [curl args...]: body in $TMP/<name>.body, headers in .head;
# prints the status code. A cold free-tier instance can take a minute to wake: generous timeout.
fetch() {
  local name=$1 method=$2 path=$3
  shift 3
  curl -sS -o "$TMP/$name.body" -D "$TMP/$name.head" -w '%{http_code}' --max-time 90 \
    -b "$JAR" -c "$JAR" -X "$method" "$@" "$BASE$path" 2>"$TMP/$name.err" || true
}
header() { grep -i "^$2:" "$TMP/$1.head" | tail -1 | cut -d' ' -f2- | tr -d '\r'; }
body_has() { grep -q -- "$2" "$TMP/$1.body"; }

status=$(fetch healthz GET /healthz)
if [ "$status" = 200 ] && body_has healthz '"ok"'; then pass "liveness /healthz"
else fail "liveness /healthz" "$status $(head -c 200 "$TMP/healthz.err")"; fi

status=$(fetch readyz GET /readyz)
if [ "$status" = 200 ] && body_has readyz '"database": "ok"'; then pass "readiness /readyz: database ok"
else fail "readiness /readyz" "$status $(head -c 200 "$TMP/readyz.body")"; fi
if [ "${EXPECT_DEMO:-0}" = 1 ]; then
  if body_has readyz 'not used (demo mode)'; then pass "demo mode: no Redis in the readiness check"
  else fail "demo mode expected" "$(head -c 200 "$TMP/readyz.body")"; fi
fi

status=$(fetch spa GET /incidents)
csp=$(header spa content-security-policy)
if [ "$status" = 200 ] && body_has spa 'id="root"'; then pass "SPA served for a client-side route"
else fail "SPA served for a client-side route" "$status"; fi
case "$csp" in
  *"script-src 'self'"*"frame-ancestors 'none'"*) pass "SPA has a Content-Security-Policy" ;;
  *) fail "SPA has a Content-Security-Policy" "${csp:-none}" ;;
esac
if [ "$(header spa x-content-type-options)" = nosniff ]; then pass "nosniff"; else fail "nosniff" "missing"; fi
if [ "${BASE#https://}" != "$BASE" ]; then
  hsts=$(header healthz strict-transport-security)
  if [ -n "$hsts" ]; then pass "HSTS over HTTPS ($hsts)"; else fail "HSTS over HTTPS" "missing"; fi
  status=$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "http://${BASE#https://}/healthz" || true)
  case "$status" in 301|302|307|308) pass "plain HTTP redirects to HTTPS" ;; 000) pass "plain HTTP not served" ;;
    *) fail "plain HTTP redirects to HTTPS" "$status" ;; esac
fi

status=$(fetch anon GET /api/v1/incidents/)
if [ "$status" = 403 ] && body_has anon '"error"'; then pass "API refuses anonymous callers with the error envelope"
else fail "API refuses anonymous callers" "$status"; fi

status=$(fetch missing GET /api/v1/no-such-endpoint/)
if [ "$status" = 404 ] && body_has missing '"not_found"'; then pass "unknown API path is a JSON 404"
else fail "unknown API path is a JSON 404" "$status"; fi

status=$(fetch link GET /a/not-a-real-token/)
if [ "$status" = 404 ] && body_has link 'Link not valid'; then pass "one-tap action links reach Django"
else fail "one-tap action links reach Django" "$status"; fi

status=$(fetch csrf GET /api/v1/auth/csrf/)
token=$(awk '$6 == "csrftoken" {print $7}' "$JAR" | tail -1)
if [ "$status" = 204 ] && [ -n "$token" ]; then pass "CSRF cookie issued"
else fail "CSRF cookie issued" "$status"; fi

if [ -n "${SMOKE_EMAIL:-}" ] && [ -n "${SMOKE_PASSWORD:-}" ]; then
  status=$(fetch login POST /api/v1/auth/login/ -H "Content-Type: application/json" \
    -H "X-CSRFToken: $token" -H "Referer: $BASE/login" \
    --data "{\"email\": \"$SMOKE_EMAIL\", \"password\": \"$SMOKE_PASSWORD\"}")
  if [ "$status" = 200 ]; then pass "sign in as $SMOKE_EMAIL"; else fail "sign in" "$status"; fi
  status=$(fetch me GET /api/v1/me/)
  if [ "$status" = 200 ] && body_has me "$SMOKE_EMAIL"; then pass "signed-in API call (/api/v1/me/)"
  else fail "signed-in API call" "$status"; fi
fi

if [ -n "${TICK_SECRET:-}" ]; then
  status=$(fetch tick POST /internal/tick/ -H "X-Tick-Secret: $TICK_SECRET")
  if [ "$status" = 200 ] && body_has tick '"healthy": true'; then pass "tick runs and reports healthy"
  else fail "tick" "$status $(head -c 300 "$TMP/tick.body")"; fi
fi

echo "smoke: $failures failure(s) against $BASE"
[ "$failures" -eq 0 ]
