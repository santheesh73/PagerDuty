"""Inbound webhooks from Twilio: delivery receipts and the "press 1" keypress on a call.

Both are authenticated only by Twilio's request signature (HMAC-SHA1 over the exact URL and form
fields, keyed by the account auth token), compared in constant time. With no auth token
configured they answer 404, as if they did not exist.
"""

import logging
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.core.errors import DomainError

from . import actions, link_actions, links, providers

logger = logging.getLogger(__name__)


def _verified_params(request: HttpRequest) -> dict[str, str]:
    if not settings.TWILIO_AUTH_TOKEN:
        raise Http404
    params = {str(k): str(v) for k, v in request.POST.items()}
    url = settings.PUBLIC_BASE_URL.rstrip("/") + request.get_full_path()
    if not providers.valid_signature(url, params, request.headers.get("X-Twilio-Signature", "")):
        raise PermissionError
    return params


@csrf_exempt
@never_cache
@require_POST
def twilio_status(request: HttpRequest) -> HttpResponse:
    try:
        params = _verified_params(request)
    except PermissionError:
        return HttpResponse(status=403)
    sid = params.get("MessageSid") or params.get("CallSid") or ""
    state = params.get("MessageStatus") or params.get("CallStatus") or ""
    if sid and state:
        actions.apply_provider_status(sid, state)
    return HttpResponse(status=204)


def _twiml(message: str) -> HttpResponse:
    return HttpResponse(
        f"<Response><Say>{escape(message)}</Say></Response>", content_type="text/xml"
    )


@csrf_exempt
@never_cache
@require_POST
def twilio_voice(request: HttpRequest, token: str) -> HttpResponse:
    """Twilio posts the digit pressed during the call. `1` acknowledges, once."""
    try:
        params = _verified_params(request)
    except PermissionError:
        return HttpResponse(status=403)
    if params.get("Digits") != "1":
        return _twiml("Not acknowledged. Goodbye.")
    try:
        link_actions.act(token, via="voice")
    except links.InvalidLink:
        return _twiml("This page was already handled. Goodbye.")
    except DomainError:
        return _twiml("This incident no longer needs acknowledging. Goodbye.")
    return _twiml("Acknowledged. Goodbye.")
