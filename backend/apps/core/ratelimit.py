"""A tiny fixed-window rate limit for plain Django views (DRF throttles only fit DRF views).

Fails open, like the API throttles: the cache is Redis, which is disposable, and refusing to
acknowledge a page because the limiter's store is down would be worse than not limiting.
"""

import logging
import time

from django.core.cache import cache, caches
from django.core.cache.backends.db import DatabaseCache
from django.db import connection, transaction
from django.http import HttpRequest
from rest_framework.throttling import BaseThrottle

logger = logging.getLogger(__name__)


def client_ident(request: HttpRequest) -> str:
    """The caller's address, honouring NUM_PROXIES the same way the API throttles do."""
    return BaseThrottle().get_ident(request)  # type: ignore[arg-type]


def hit(key: str, window: int) -> int:
    """Count one event; return how many there have been since the first, within `window` seconds.

    The window opens at the first event and closes `window` seconds later, on any cache backend.
    Redis keeps a key's TTL on `incr`, but Django's database cache (demo mode) resets it to the
    300 s default on every `incr`: relying on that once held a one-minute limit closed for good
    and cut a 15-minute lockout to five. So the window's start is stored, and both keys' expiry is
    pinned to its end after each count.
    """
    if isinstance(caches["default"], DatabaseCache):
        # Its `incr` is get-then-set, so racing workers lose increments (16 hits counted as 2 to 5).
        # An advisory lock per key, inside one transaction, makes the count atomic.
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [key])
            return _hit(key, window)
    return _hit(key, window)


def _hit(key: str, window: int) -> int:
    now = time.time()
    cache.add(f"{key}:start", now, timeout=window)
    started = float(cache.get(f"{key}:start") or now)
    remaining = max(1, int(started + window - now))
    cache.add(key, 0, timeout=remaining)
    hits = int(cache.incr(key))
    cache.touch(key, timeout=remaining)
    cache.touch(f"{key}:start", timeout=remaining)
    return hits


def count(key: str) -> int:
    return int(cache.get(key) or 0)


def reset(key: str) -> None:
    cache.delete_many([key, f"{key}:start"])


def allow(scope: str, request: HttpRequest, *, limit: int, window: int = 60) -> bool:
    try:
        return hit(f"rl:{scope}:{client_ident(request)}", window) <= limit
    except Exception as exc:
        logger.warning("rate limiter unavailable (%s); allowing", type(exc).__name__)
        return True
