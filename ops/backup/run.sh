#!/usr/bin/env bash
# Run backup.sh now and then every BACKUP_INTERVAL_SECONDS (default 24 h). A failed run is logged
# and retried next interval; the container's health check goes unhealthy when the last
# successful backup is older than twice the interval, so a stuck job is visible to `docker ps`.
set -u
interval="${BACKUP_INTERVAL_SECONDS:-86400}"
while true; do
  if /usr/local/bin/backup.sh; then
    touch /tmp/last-backup-ok
  else
    echo "run-backups: backup FAILED; retrying in ${interval}s" >&2
  fi
  sleep "$interval" &
  wait $!
done
