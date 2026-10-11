"""JSON error responses for /api/ paths that never reach a DRF view.

DRF's exception handler covers exceptions raised inside API views. These cover the rest: a path
that matches no route (404), an unhandled crash (500), and a body over the size limit rejected
before any view runs (413). Everything under /api/ answers with the one error envelope, so a client
never has to parse an HTML error page.
"""

from collections.abc import Callable

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views import defaults

from .logging import get_request_id


def envelope(code: str, message: str, status: int) -> JsonResponse:
    return JsonResponse({"error": {"code": code, "message": message, "details": {}}}, status=status)


def _is_api(request: HttpRequest) -> bool:
    return request.path.startswith("/api/")


def not_found(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    if _is_api(request):
        return envelope("not_found", "No such endpoint.", 404)
    return defaults.page_not_found(request, exception)


def server_error(request: HttpRequest) -> HttpResponse:
    if _is_api(request):
        # The id the logs carry (validated or generated), never raw header input.
        request_id = get_request_id()
        return envelope(
            "server_error",
            "Something went wrong on our side. It has been logged"
            + (f" (request {request_id})." if request_id else "."),
            500,
        )
    return defaults.server_error(request)


class BodySizeLimitMiddleware:
    """413 with the JSON envelope for an API body over DATA_UPLOAD_MAX_MEMORY_SIZE, before any view
    or throttle reads it. (Django would otherwise answer 400 with an HTML page, and only once
    something tried to read the body.)"""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        limit = settings.DATA_UPLOAD_MAX_MEMORY_SIZE
        if _is_api(request) and limit is not None:
            try:
                length = int(request.headers.get("Content-Length") or 0)
            except ValueError:
                return envelope("bad_request", "Invalid Content-Length.", 400)
            if length > limit:
                return too_large()
        return self.get_response(request)


def too_large() -> JsonResponse:
    limit = settings.DATA_UPLOAD_MAX_MEMORY_SIZE
    return envelope("payload_too_large", f"Request bodies are limited to {limit} bytes.", 413)


__all__ = ["BodySizeLimitMiddleware", "RequestDataTooBig", "not_found", "server_error", "too_large"]
