"""Response headers Django does not set itself, and the admin-MFA enrolment gate."""

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

PERMISSIONS_POLICY = (
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), "
    "microphone=(), payment=(), usb=(), interest-cohort=()"
)

# What an admin who has not enrolled MFA yet may still reach: enough to enrol (or leave).
ENROLMENT_PATHS = (
    "/api/v1/me/",
    "/api/v1/me/mfa/",
    "/api/v1/auth/",
)


class SecurityHeadersMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        response.headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response


class MfaEnrolmentMiddleware:
    """With REQUIRE_MFA_FOR_ADMINS, an admin without MFA can do nothing but enrol.

    A middleware rather than a DRF permission so that it also covers the Django admin and any
    future view that forgets to list a permission class.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if settings.REQUIRE_MFA_FOR_ADMINS and self._gated(request):
            from . import mfa

            user = request.user
            if mfa.required(user) and not mfa.enabled(user):
                return JsonResponse(
                    {
                        "error": {
                            "code": "mfa_enrollment_required",
                            "message": "Team admins must set up two-factor authentication first.",
                            "details": {},
                        }
                    },
                    status=403,
                )
        return self.get_response(request)

    @staticmethod
    def _gated(request: HttpRequest) -> bool:
        path = request.path
        if not (path.startswith("/api/v1/") or path.startswith("/admin/")):
            return False
        if path == "/api/v1/me/" or path.startswith(ENROLMENT_PATHS[1:]):
            return False
        user = getattr(request, "user", None)
        return bool(user is not None and user.is_authenticated)
