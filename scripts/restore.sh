#!/usr/bin/env bash
# Restore a Pulse dump into a database.
#
#   scripts/restore.sh backups/daily/pulse-<stamp>.dump postgres://user:pass@host:5432/target_db
#
# The target database must already exist (empty or not: objects are dropped and recreated).
# The restore runs in ONE transaction, so a failure leaves the target as it was, never half
# restored. Restoring over the live database needs CONFIRM_OVERWRITE=yes: the point of this
# script is normally to restore into a scratch database first and look.
set -euo pipefail

file="${1:?usage: restore.sh <dump> <target-database-url>}"
target="${2:?usage: restore.sh <dump> <target-database-url>}"
[ -f "$file" ] || { echo "restore: no such file: $file" >&2; exit 1; }

# Which database a URL points at, ignoring how it is spelled: credentials, query string, the host
# aliases for this machine and the default port. (Comparing the strings let `localhost` against
# `127.0.0.1` restore over the live database without the confirmation.)
database_of() {
  local rest="${1#*://}" hostport db host port
  rest="${rest#*@}"; rest="${rest%%\?*}"
  hostport="${rest%%/*}"; db="${rest#*/}"
  case "$hostport" in
    "["*"]:"*) host="${hostport%%]*}]"; port="${hostport##*:}" ;;
    "["*"]") host="$hostport"; port=5432 ;;
    *:*) host="${hostport%%:*}"; port="${hostport##*:}" ;;
    *) host="$hostport"; port=5432 ;;
  esac
  case "$host" in localhost | 127.0.0.1 | 0.0.0.0 | "[::1]" | "") host=localhost ;; esac
  echo "$host:$port/$db"
}

if [ -n "${DATABASE_URL:-}" ] && [ "$(database_of "$target")" = "$(database_of "$DATABASE_URL")" ] \
  && [ "${CONFIRM_OVERWRITE:-}" != "yes" ]; then
  echo "restore: target is the live DATABASE_URL; set CONFIRM_OVERWRITE=yes to overwrite it" >&2
  exit 2
fi

if [ -f "$file.sha256" ]; then
  (cd "$(dirname "$file")" && sha256sum --check --status "$(basename "$file").sha256") \
    || { echo "restore: checksum mismatch, refusing to restore a corrupt dump" >&2; exit 1; }
fi

echo "restore: $file -> target"
pg_restore --clean --if-exists --no-owner --no-privileges --single-transaction \
  --exit-on-error --dbname "$target" "$file"
echo "restore: ok"
