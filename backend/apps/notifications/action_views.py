"""The one-tap acknowledge/resolve page behind the links in pages.

GET only *shows* a confirmation. Mail scanners, SMS link previews and chat unfurlers fetch URLs
automatically, and a GET that acted would let them acknowledge an incident nobody has seen.
Only the POST from the page spends the link.
"""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from apps.core import ratelimit
from apps.core.errors import DomainError

from . import link_actions, links
from .models import ActionLink

RATE_LIMIT_PER_MINUTE = 30
INVALID = "This link is invalid, has expired, or was already used."


def _page(request: HttpRequest, status: int, heading: str, **context: object) -> HttpResponse:
    response = render(
        request, "notifications/action_link.html", {"heading": heading, **context}, status=status
    )
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex"
    return response


@never_cache
@require_http_methods(["GET", "POST"])
def action_link(request: HttpRequest, token: str) -> HttpResponse:
    if not ratelimit.allow("action-link", request, limit=RATE_LIMIT_PER_MINUTE):
        return _page(request, 429, "Slow down", message="Too many attempts. Try again in a minute.")

    if request.method == "GET":
        try:
            link = links.load(token)
            link_actions.check_actor(link)
        except links.InvalidLink:
            return _page(request, 404, "Link not valid", message=INVALID)
        acknowledging = link.action == ActionLink.Action.ACK
        return _page(
            request,
            200,
            "Acknowledge this incident?" if acknowledging else "Resolve this incident?",
            incident=link.notification.incident,
            confirm="Acknowledge" if acknowledging else "Resolve",
            danger=not acknowledging,
        )

    try:
        link = link_actions.act(token, via="link")
    except links.InvalidLink:
        return _page(request, 404, "Link not valid", message=INVALID)
    except DomainError as exc:
        return _page(request, 409, "Nothing to do", message=exc.message)
    done = "Acknowledged" if link.action == ActionLink.Action.ACK else "Resolved"
    return _page(
        request, 200, done, incident=link.notification.incident, message="You can close this page."
    )
