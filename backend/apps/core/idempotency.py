"""`Idempotency-Key` for API writes: retry a POST/PATCH/DELETE safely after a timeout.

A client that never saw the response to a write (network drop, proxy timeout) can send the same
request again with the same `Idempotency-Key` header and get the original response back, with
`Idempotent-Replayed: true`, instead of acting twice. Reusing a key with a different body is an
error (422), and a retry that arrives while the first attempt is still running gets 409.

Keys are scoped to the caller (the signed-in user, or for the Events API the routing key) and
remembered for 24 hours in the cache. Redis is disposable, so this is a retry convenience, not the
correctness guarantee: paging is already idempotent in Postgres (dedup keys, unique notification
keys). If the cache is down the header is ignored and the request runs normally.

A response marked `Cache-Control: no-store` carries a secret shown once (a new integration key,
an MFA secret, backup codes). Only a tombstone is kept for it, never the body: a retry gets 409
`idempotency_response_withheld` rather than the secret, and the request still runs only once.
"""

import contextlib
import hashlib
import json
import logging
import re
from collections.abc import Callable

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse

from .api_errors import envelope

logger = logging.getLogger(__name__)

HEADER = "Idempotency-Key"
TTL = 24 * 3600
IN_FLIGHT_TTL = 60
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_VALID = re.compile(r"^[A-Za-z0-9_.:\-]{1,255}$")


def _scope(request: HttpRequest) -> str | None:
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return f"user:{user.pk}"
    if request.path == "/api/v1/events/":
        try:
            routing_key = str(json.loads(request.body or b"{}").get("routing_key", ""))
        except (ValueError, AttributeError):
            return None
        if routing_key:
            return "rk:" + hashlib.sha256(routing_key.encode()).hexdigest()[:32]
    return None  # anonymous auth endpoints: nothing to scope by, so no replay


class IdempotencyMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        key = request.headers.get(HEADER)
        if (
            key is None
            or request.method not in WRITE_METHODS
            or not request.path.startswith("/api/v1/")
        ):
            return self.get_response(request)
        if not _VALID.match(key):
            return envelope(
                "invalid_idempotency_key", "Use 1-255 letters, digits, _ . : or -.", 400
            )
        scope = _scope(request)
        if scope is None:
            return self.get_response(request)

        name = hashlib.sha256(f"{scope}|{request.method}|{request.path}|{key}".encode()).hexdigest()
        stored_key, lock_key = f"idem:{name}", f"idem-lock:{name}"
        fingerprint = hashlib.sha256(request.body or b"").hexdigest()
        try:
            stored = cache.get(stored_key)
            if stored is not None:
                if stored["fingerprint"] != fingerprint:
                    return envelope(
                        "idempotency_key_reused",
                        "This Idempotency-Key was used with a different request body.",
                        422,
                    )
                if stored.get("withheld"):
                    return envelope(
                        "idempotency_response_withheld",
                        "The request with this Idempotency-Key already succeeded. Its response held"
                        " a secret that is shown only once, so it is not replayed.",
                        409,
                    )
                response = HttpResponse(
                    stored["body"], status=stored["status"], content_type=stored["content_type"]
                )
                response["Idempotent-Replayed"] = "true"
                return response
            if not cache.add(lock_key, 1, timeout=IN_FLIGHT_TTL):
                return envelope(
                    "idempotency_in_progress",
                    "A request with this Idempotency-Key is still being processed.",
                    409,
                )
        except Exception as exc:  # the cache is disposable: run the request without replay
            logger.warning("idempotency cache unavailable (%s)", type(exc).__name__)
            return self.get_response(request)

        try:
            response = self.get_response(request)
            if response.status_code < 500 and not getattr(response, "streaming", False):
                if "no-store" in response.get("Cache-Control", ""):
                    entry = {"fingerprint": fingerprint, "withheld": True}
                else:
                    if hasattr(response, "render") and not getattr(response, "is_rendered", True):
                        response.render()
                    entry = {
                        "fingerprint": fingerprint,
                        "status": response.status_code,
                        "body": response.content,
                        "content_type": response.get("Content-Type", "application/json"),
                    }
                cache.set(stored_key, entry, timeout=TTL)
            return response
        finally:
            with contextlib.suppress(Exception):  # best effort; the lock expires on its own
                cache.delete(lock_key)
