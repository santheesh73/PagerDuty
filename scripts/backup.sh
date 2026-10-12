#!/usr/bin/env bash
# Back up the Pulse database: pg_dump -Fc, verified, checksummed, rotated, optionally uploaded.
#
#   DATABASE_URL=postgres://... scripts/backup.sh
#
# Environment (all optional except DATABASE_URL):
#   BACKUP_DIR              where dumps live (default ./backups); daily/ and weekly/ below it
#   BACKUP_RETAIN_DAILY     newest daily dumps to keep (default 7)
#   BACKUP_RETAIN_WEEKLY    newest weekly dumps to keep (default 4)
#   BACKUP_WEEKLY_DOW       ISO weekday (1=Mon..7=Sun) whose dump is also kept as weekly (default 7)
#   BACKUP_S3_BUCKET        upload each dump to this S3-compatible bucket (needs the aws CLI)
#   BACKUP_S3_PREFIX        key prefix (default pulse)
#   BACKUP_S3_ENDPOINT      endpoint URL for non-AWS stores (R2, B2, MinIO, Wasabi...)
#   BACKUP_S3_REGION        region (default us-east-1)
#   BACKUP_S3_ACCESS_KEY_ID / BACKUP_S3_SECRET_ACCESS_KEY   credentials for that store
#   BACKUP_S3_SSE           server-side encryption mode, e.g. AES256 (default: none)
#   BACKUP_HEARTBEAT_URL    GET after a fully successful run (dead-man's switch for backups)
#
# Exit status is non-zero if the dump, its verification, or the upload fails, and the heartbeat
# is then NOT sent, so a monitor notices a backup job that quietly stopped working.
# Remote retention is the bucket's lifecycle rule; this script only rotates the local copies.
set -euo pipefail

: "${DATABASE_URL:?set DATABASE_URL}"
DIR="${BACKUP_DIR:-./backups}"
KEEP_DAILY="${BACKUP_RETAIN_DAILY:-7}"
KEEP_WEEKLY="${BACKUP_RETAIN_WEEKLY:-4}"
WEEKLY_DOW="${BACKUP_WEEKLY_DOW:-7}"

mkdir -p "$DIR/daily" "$DIR/weekly"
stamp="${BACKUP_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}" # BACKUP_STAMP only exists so tests get stable names
name="pulse-$stamp.dump"
partial="$DIR/.$name.partial"
trap 'rm -f "$partial"' EXIT

echo "backup: dumping to $DIR/daily/$name"
pg_dump --format=custom --no-owner --no-privileges --dbname "$DATABASE_URL" --file "$partial"

# A dump that cannot be read back is not a backup: list its table of contents before trusting it.
if ! pg_restore --list "$partial" >/dev/null; then
  echo "backup: FAILED verification (pg_restore --list)" >&2
  exit 1
fi
if [ ! -s "$partial" ]; then
  echo "backup: FAILED, dump is empty" >&2
  exit 1
fi

mv "$partial" "$DIR/daily/$name"
(cd "$DIR/daily" && sha256sum "$name" > "$name.sha256")

if [ "$(date -u +%u)" = "$WEEKLY_DOW" ]; then
  cp "$DIR/daily/$name" "$DIR/daily/$name.sha256" "$DIR/weekly/"
fi

# Rotate only after a verified new dump exists, so a failing job never deletes the last good one.
prune() { # dir keep
  local dir="$1" keep="$2" f
  # An empty directory makes `ls` exit 2, which pipefail would turn into a failed backup (on
  # every day but the weekly one, `weekly/` is empty): nothing to prune is not an error.
  # shellcheck disable=SC2012
  { ls -1t "$dir"/pulse-*.dump 2>/dev/null || true; } | tail -n +"$((keep + 1))" | while read -r f; do
    rm -f "$f" "$f.sha256"
  done
}
prune "$DIR/daily" "$KEEP_DAILY"
prune "$DIR/weekly" "$KEEP_WEEKLY"

if [ -n "${BACKUP_S3_BUCKET:-}" ]; then
  command -v aws >/dev/null || { echo "backup: BACKUP_S3_BUCKET set but the aws CLI is missing" >&2; exit 1; }
  dest="s3://${BACKUP_S3_BUCKET}/${BACKUP_S3_PREFIX:-pulse}/daily/$name"
  args=(s3 cp "$DIR/daily/$name" "$dest" --only-show-errors)
  [ -n "${BACKUP_S3_ENDPOINT:-}" ] && args+=(--endpoint-url "$BACKUP_S3_ENDPOINT")
  [ -n "${BACKUP_S3_SSE:-}" ] && args+=(--sse "$BACKUP_S3_SSE")
  echo "backup: uploading to $dest"
  AWS_ACCESS_KEY_ID="${BACKUP_S3_ACCESS_KEY_ID:-${AWS_ACCESS_KEY_ID:-}}" \
  AWS_SECRET_ACCESS_KEY="${BACKUP_S3_SECRET_ACCESS_KEY:-${AWS_SECRET_ACCESS_KEY:-}}" \
  AWS_DEFAULT_REGION="${BACKUP_S3_REGION:-us-east-1}" \
    aws "${args[@]}"
fi

if [ -n "${BACKUP_HEARTBEAT_URL:-}" ]; then
  curl -fsS -m 10 -o /dev/null "$BACKUP_HEARTBEAT_URL" || echo "backup: heartbeat ping failed (non-fatal)" >&2
fi

echo "backup: ok $DIR/daily/$name ($(wc -c < "$DIR/daily/$name") bytes)"
