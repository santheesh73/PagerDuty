import logging
import re
import time
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from . import metrics
from .logging import REQUEST_ID_HEADER, new_request_id, reset_request_id, set_request_id

# Accept a caller-supplied ID only if it looks like one; never echo arbitrary header input.
_VALID_ID = re.compile(r"^[A-Za-z0-9_.-]{8,64}$")


class RequestIDMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        rid = incoming if _VALID_ID.match(incoming) else new_request_id()
        token = set_request_id(rid)
        try:
            response = self.get_response(request)
        finally:
            reset_request_id(token)
        response[REQUEST_ID_HEADER] = rid
        return response


access_log = logging.getLogger("pulse.access")
_QUIET = {"healthz", "readyz", "metrics"}


class ObservabilityMiddleware:
    """One JSON access-log line and the HTTP metrics per request.

    Logs method, route *template*, status and duration only. Never the query string, headers or
    body: those carry session cookies, passwords and integration keys (a test pins this).
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        started = time.perf_counter()
        status = 500
        try:
            response = self.get_response(request)
            status = response.status_code
            return response
        finally:
            elapsed = time.perf_counter() - started
            route = metrics.route_template(request)
            if route.strip("/") not in _QUIET:
                user = getattr(request, "user", None)
                access_log.info(
                    "request",
                    extra={
                        "method": request.method,
                        "route": route,
                        "status": status,
                        "duration_ms": round(elapsed * 1000, 1),
                        "user_id": user.pk if user is not None and user.is_authenticated else None,
                    },
                )
            metrics.observe_request(request, status, elapsed)
