"""Liveness and readiness probes.

`/healthz` answers "is the process up?" and touches nothing, so an orchestrator never
restarts a healthy web process because Postgres blipped. `/readyz` answers "can this
instance serve traffic?" and checks both backing stores.
"""

from django.conf import settings
from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET
from redis import Redis
from redis.exceptions import RedisError


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
    try:
        Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1).ping()
        checks["redis"] = "ok"
    except RedisError as exc:
        checks["redis"] = f"error: {exc.__class__.__name__}"
    ready = all(v == "ok" for v in checks.values())
    return JsonResponse(
        {"status": "ok" if ready else "unavailable", "checks": checks}, status=200 if ready else 503
    )
