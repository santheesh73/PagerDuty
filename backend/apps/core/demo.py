"""Guards for the public demo (DEMO_MODE), whose logins are shared and printed on the sign-in page.

A password change, or turning two-factor authentication on, on a shared login would lock every
other visitor out until the next reset. So while DEMO_MODE is on, the seeded accounts cannot
change their own credentials. Everything else stays open: a visitor can trigger, acknowledge and
resolve incidents, and edit services, policies and schedules. `DEMO_RESET_HOURS` reseeds the
whole demo periodically to undo the rest.
"""

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from .api_errors import envelope

DEMO_EMAIL_SUFFIX = "@demo.local"  # every account `seed_demo` creates
LOCKED_PATHS = frozenset(
    {
        "/api/v1/me/password/",
        "/api/v1/me/mfa/setup/",
        "/api/v1/me/mfa/confirm/",
        "/api/v1/me/mfa/disable/",
        "/api/v1/me/mfa/backup-codes/",
    }
)


def is_demo_account(user: object) -> bool:
    email = getattr(user, "email", "") or ""
    return bool(getattr(user, "is_authenticated", False)) and email.lower().endswith(
        DEMO_EMAIL_SUFFIX
    )


class DemoAccountGuardMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if (
            settings.DEMO_MODE
            and request.method not in ("GET", "HEAD", "OPTIONS")
            and request.path in LOCKED_PATHS
            and is_demo_account(getattr(request, "user", None))
        ):
            return envelope(
                "demo_account_locked",
                "The shared demo accounts can't change their password or two-factor settings.",
                403,
            )
        return self.get_response(request)
