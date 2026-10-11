"""`POST /internal/tick/`: Beat's job, for deployments that have no Beat (demo mode).

A free hosting tier gives one web process and no background workers, so an external scheduler (a
GitHub Actions cron, cron-job.org) calls this instead. Each call does what the Beat schedule would
have done since the last one: escalate due incidents, send due and retried pages, end expired
maintenance and debug windows, and stamp the heartbeat. With DEMO_RESET_HOURS it also reseeds a
public demo every so often. It then pings the dead-man's switch if the stack is healthy. Every
step is idempotent and safe to run concurrently, so a doubled or overlapping tick cannot page
anyone twice.

Off unless DEMO_MODE is on and TICK_SECRET is set. The secret is compared in constant time, and
calls are rate limited per address before the secret is even looked at.

With DEMO_SELF_TICK_SECONDS the demo also ticks itself: after a request's response has been sent,
at most once per that many seconds. Timers then advance whenever someone is using the demo, with no
scheduler configured; the external one only matters while it is idle.
"""

import hmac
import io
import logging
from datetime import datetime
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.catalog import actions as catalog_actions
from apps.escalations import engine
from apps.notifications import actions as notification_actions

from . import heartbeat, ratelimit, retention, selfcheck
from .api_errors import envelope

logger = logging.getLogger(__name__)

HEADER = "X-Tick-Secret"
RATE_LIMIT_PER_MINUTE = 12
HOUSEKEEPING_EVERY = 24 * 3600  # retention and expired sessions, as Beat runs them daily


def run(now: datetime | None = None) -> dict[str, Any]:
    now = now or timezone.now()
    result: dict[str, Any] = {}
    hours = settings.DEMO_RESET_HOURS
    if hours and cache.add("pulse:tick:demo-reset", 1, timeout=hours * 3600):
        call_command("seed_demo", "--reset", stdout=io.StringIO())
        result["demo_reset"] = True
    result |= {
        "escalated": engine.sweep(now),
        "notifications_sent": notification_actions.deliver_due(now=now),
        "modes_expired": catalog_actions.expire_service_modes(now=now),
    }
    if cache.add("pulse:tick:housekeeping", 1, timeout=HOUSEKEEPING_EVERY):
        retention.clear_expired_sessions(now=now)
        result["purged"] = retention.purge(settings.RETENTION_DAYS, now=now)
    heartbeat.record(now.timestamp())
    result["healthy"] = all(check.ok for check in selfcheck.run(include_beat=False, now=now))
    result["heartbeat_pinged"] = result["healthy"] and heartbeat.ping_external()
    return result


def self_tick(**_: Any) -> None:
    """`request_finished` receiver (see CoreConfig.ready): the response has already gone out."""
    seconds = settings.DEMO_SELF_TICK_SECONDS
    if not (settings.DEMO_MODE and seconds):
        return
    try:
        if cache.add("pulse:tick:self", 1, timeout=seconds):
            run()
    except Exception:
        logger.exception("self-tick failed; the next request or scheduled tick retries")


@csrf_exempt
@never_cache
@require_POST
def tick(request: HttpRequest) -> JsonResponse:
    if not (settings.DEMO_MODE and settings.TICK_SECRET):
        return envelope("not_found", "No such endpoint.", 404)
    if not ratelimit.allow("tick", request, limit=RATE_LIMIT_PER_MINUTE):
        return envelope("throttled", "Too many ticks; at most one every few seconds.", 429)
    supplied = request.headers.get(HEADER, "")
    if not hmac.compare_digest(supplied.encode(), settings.TICK_SECRET.encode()):
        logger.warning("tick refused: missing or wrong %s", HEADER)
        return envelope("permission_denied", f"A valid {HEADER} header is required.", 403)
    result = run()
    logger.info("tick", extra={"tick": result})
    return JsonResponse(result)
