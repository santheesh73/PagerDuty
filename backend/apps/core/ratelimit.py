"""A tiny fixed-window rate limit for plain Django views (DRF throttles only fit DRF views).

Fails open, like the API throttles: the cache is Redis, which is disposable, and refusing to
acknowledge a page because the limiter's store is down would be worse than not limiting.
"""

import logging

from django.core.cache import cache
from django.http import HttpRequest
from rest_framework.throttling import BaseThrottle

logger = logging.getLogger(__name__)


def client_ident(request: HttpRequest) -> str:
    """The caller's address, honouring NUM_PROXIES the same way the API throttles do."""
    return BaseThrottle().get_ident(request)  # type: ignore[arg-type]


def allow(scope: str, request: HttpRequest, *, limit: int, window: int = 60) -> bool:
    key = f"rl:{scope}:{client_ident(request)}"
    try:
        cache.add(key, 0, timeout=window)
        return cache.incr(key) <= limit
    except Exception as exc:
        logger.warning("rate limiter unavailable (%s); allowing", type(exc).__name__)
        return True
