"""Throttles that fail open.

Throttle counters live in Redis. Redis is disposable by design, so if it's unreachable we
log and let the request through: dropping an alert because the rate limiter is down would
be far worse than briefly not rate limiting.
"""

import hashlib
import logging
from typing import Any

from redis.exceptions import RedisError
from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

# Only a broken cache is a reason to let a request through. Anything else (a body too large to
# read, a bug) must surface: catching everything once logged an oversized request as "throttle
# backend unavailable" and let it reach the view.
CACHE_ERRORS: tuple[type[BaseException], ...] = (RedisError, ConnectionError, TimeoutError, OSError)


class FailOpenMixin:
    def allow_request(self, request: Request, view: APIView) -> bool:
        try:
            return super().allow_request(request, view)  # type: ignore[misc]
        except CACHE_ERRORS as exc:
            # One line, no traceback: with Redis down this fires on every request.
            logger.warning(
                "throttle backend unavailable (%s: %s); allowing request",
                type(exc).__name__,
                str(exc)[:120],
            )
            return True


class AddressThrottle(FailOpenMixin, SimpleRateThrottle):
    """Per client address, signed in or not.

    DRF's AnonRateThrottle stops counting once a request carries a session, so anyone signed
    in to one account could guess another account's password or codes without a limit.
    """

    def get_cache_key(self, request: Request, view: APIView) -> str | None:
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class LoginThrottle(AddressThrottle):
    scope = "login"


class RoutingKeyThrottle(FailOpenMixin, SimpleRateThrottle):
    """Per integration key, so one noisy monitor can't starve every other service."""

    scope = "events"

    def get_cache_key(self, request: Request, view: APIView) -> str | None:
        data: Any = request.data if isinstance(request.data, dict) else {}
        key = data.get("routing_key")
        if not isinstance(key, str) or not key:
            return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
        # Hash-free is fine: the cache is server-side, but never log the raw key.
        # A digest, so raw keys never become Redis key names (visible to anyone with redis-cli).
        digest = hashlib.sha256(str(key).encode()).hexdigest()[:32]
        return self.cache_format % {"scope": self.scope, "ident": f"rk:{digest}"}
