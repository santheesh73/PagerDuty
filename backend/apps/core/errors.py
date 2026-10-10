"""One error envelope for every API response: {"error": {"code", "message", "details"}}.

Domain code raises `DomainError` subclasses; this handler is the only place that knows
how they map to HTTP, so actions stay free of transport concerns.
"""

from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class DomainError(Exception):
    code: str = "domain_error"
    http_status: int = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str = "", details: dict[str, Any] | None = None) -> None:
        super().__init__(message or self.code)
        self.message = message or self.code.replace("_", " ")
        self.details = details or {}


class InvalidTransition(DomainError):
    code = "invalid_transition"
    http_status = status.HTTP_409_CONFLICT


class LimitExceeded(DomainError):
    code = "limit_exceeded"
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY


class Conflict(DomainError):
    code = "conflict"
    http_status = status.HTTP_409_CONFLICT


def _envelope(code: str, message: str, details: Any, http_status: int) -> Response:
    return Response(
        {"error": {"code": code, "message": message, "details": details or {}}},
        status=http_status,
    )


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, DomainError):
        return _envelope(exc.code, exc.message, exc.details, exc.http_status)
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = drf_exception_handler(exc, context)
    if response is None:
        return None  # unhandled -> Django's 500 path, logged with the request ID

    if isinstance(exc, exceptions.ValidationError):
        # 422: the request was well-formed but semantically invalid.
        return _envelope(
            "validation_error",
            "Request validation failed.",
            response.data,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    if isinstance(exc, exceptions.APIException):
        detail = response.data.get("detail", "") if isinstance(response.data, dict) else ""
        code = exc.get_codes() if isinstance(exc.get_codes(), str) else exc.default_code
        envelope = _envelope(
            str(code), str(detail) or str(exc.default_detail), {}, response.status_code
        )
        for header in ("Retry-After", "WWW-Authenticate"):
            if header in response:
                envelope[header] = response[header]
        return envelope
    return response
