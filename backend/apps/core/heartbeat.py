"""Beat liveness and the dead-man's switch.

A Beat task fires every minute. Each run proves the whole chain (Beat -> broker -> worker),
stamps a timestamp that `/metrics` and `manage.py selfcheck` read, and, only if the stack is
healthy, pings `HEARTBEAT_URL` (healthchecks.io, Better Stack, Cronitor...). The external
service alerts on *silence*, so it still fires when Pulse itself, its alerting or the host is
down: the failure that no in-stack alert can report.
"""

import logging
import time
import urllib.request

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

KEY = "pulse:beat:last_run"
BEAT_STALE_AFTER = 180  # three missed one-minute beats


def record(now: float | None = None) -> None:
    cache.set(KEY, now if now is not None else time.time(), None)


def last_run() -> float | None:
    try:
        value = cache.get(KEY)
    except Exception:  # Redis is disposable; "unknown" is a valid answer
        return None
    return float(value) if value is not None else None


def ping_external(url: str | None = None) -> bool:
    """GET the dead-man's-switch URL. Never raises: a monitor outage must not fail the task."""
    url = url or settings.HEARTBEAT_URL
    if not url:
        return False
    if not url.startswith(("https://", "http://")):
        logger.error("HEARTBEAT_URL must be http(s); not pinging")
        return False
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "pulse-heartbeat"})  # noqa: S310
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
            return 200 <= response.status < 300
    except Exception as exc:
        logger.warning("heartbeat ping failed (%s)", type(exc).__name__)
        return False
