"""Liveness and readiness probes.

`/healthz` answers "is the process up?" and touches nothing, so an orchestrator never
restarts a healthy web process because Postgres blipped. `/readyz` answers "can this
instance serve traffic?" and checks both backing stores: Postgres is required (503 without
it); Redis is not, because Pulse commits alerts and pages without it and the sweepers catch
up, so a Redis outage is reported as `degraded` with a 200.
"""

import logging

from django.conf import settings
from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET
from redis import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


@require_GET
def healthz(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


@require_GET
def readyz(request: HttpRequest) -> JsonResponse:
    checks: dict[str, str] = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:  # any driver error means "not ready"
        checks["database"] = f"error: {exc.__class__.__name__}"
        # The probe body stays terse (it is public); the reason goes to the log.
        logger.warning("readyz: database check failed: %s", str(exc)[:300])
    try:
        Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1).ping()
        checks["redis"] = "ok"
    except RedisError as exc:
        checks["redis"] = f"error: {exc.__class__.__name__}"
        logger.warning("readyz: redis check failed: %s", str(exc)[:300])
    if checks["database"] != "ok":
        status, code = "unavailable", 503
    elif checks["redis"] != "ok":
        status, code = "degraded", 200
    else:
        status, code = "ok", 200
    return JsonResponse({"status": status, "checks": checks}, status=code)
