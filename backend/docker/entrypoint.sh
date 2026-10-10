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
    exec gunicorn config.wsgi:application \
      --bind 0.0.0.0:8000 \
      --workers "${GUNICORN_WORKERS:-3}" \
      --timeout 30 \
      --access-logfile - "$@"
    ;;
  worker)
    # escalations is listed first: the worker drains it before anything else.
    exec celery -A config worker -Q escalations,notifications,default \
      --concurrency "${CELERY_CONCURRENCY:-4}" --loglevel INFO "$@"
    ;;
  beat)
    exec celery -A config beat --loglevel INFO --schedule /tmp/celerybeat-schedule "$@"
    ;;
  *)
    exec "$role" "$@"
    ;;
esac
