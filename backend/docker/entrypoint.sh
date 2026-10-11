#!/bin/sh
# Role-based entrypoint: `api` migrates (and optionally seeds) before serving;
# `worker` and `beat` wait for the API container to have migrated via depends_on.
set -eu

role="${1:-api}"
shift || true

case "$role" in
  api)
    python manage.py migrate --noinput
    if [ "${SEED_DEMO:-0}" = "1" ]; then
      python manage.py seed_demo
    fi
    # Request metrics are counted per gunicorn worker and merged at scrape time through files
    # in this directory (prometheus_client multiprocess mode). Start clean: stale files from a
    # previous run would resurrect old counters.
    export PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-/tmp/pulse-prometheus}"
    rm -rf "$PROMETHEUS_MULTIPROC_DIR"
    mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
    # No gunicorn access log: the app writes one JSON line per request (route template,
    # status, duration, request id) so logs stay structured and never carry query strings.
    exec gunicorn config.wsgi:application \
      --config /app/docker/gunicorn.conf.py \
      --bind 0.0.0.0:8000 \
      --workers "${GUNICORN_WORKERS:-3}" \
      --timeout 30 "$@"
    ;;
  worker)
    # -Q order is NOT a priority (kombu's Redis transport round-robins its queues), so
    # paging is only isolated from notification backlogs by running a worker that consumes
    # nothing else: CELERY_QUEUES=escalations. One process serving all three is the default.
    exec celery -A config worker -Q "${CELERY_QUEUES:-escalations,notifications,default}" \
      --concurrency "${CELERY_CONCURRENCY:-4}" --loglevel INFO "$@"
    ;;
  beat)
    exec celery -A config beat --loglevel INFO --schedule /tmp/celerybeat-schedule "$@"
    ;;
  *)
    exec "$role" "$@"
    ;;
esac
