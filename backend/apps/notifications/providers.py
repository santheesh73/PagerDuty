"""Twilio, over its plain REST API (no SDK dependency).

Used by the SMS and voice channels and by phone verification. `TWILIO_API_BASE` exists so tests
can point it at a local fake server; nothing in the suite ever reaches the real service.

Failure classification matters for paging: a 5xx, 429 or network error is transient (retried);
a 4xx such as an invalid number will never succeed, so it is permanent and fails at once instead
of burning retries while a human waits.
"""

import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping

from django.conf import settings

from .errors import ChannelError, PermanentChannelError

TIMEOUT = 10


def configured() -> bool:
    return bool(
        settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_FROM_NUMBER
    )


def _post(resource: str, fields: Mapping[str, str]) -> dict:
    if not configured():
        raise PermanentChannelError("Twilio is not configured on this server")
    url = (
        f"{settings.TWILIO_API_BASE.rstrip('/')}/2010-04-01/Accounts/"
        f"{settings.TWILIO_ACCOUNT_SID}/{resource}.json"
    )
    credentials = f"{settings.TWILIO_ACCOUNT_SID}:{settings.TWILIO_AUTH_TOKEN}".encode()
    request = urllib.request.Request(  # noqa: S310 - base URL is operator configuration
        url,
        data=urllib.parse.urlencode(fields).encode(),
        headers={"Authorization": "Basic " + base64.b64encode(credentials).decode()},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
            return dict(json.load(response))
    except urllib.error.HTTPError as exc:
        detail = exc.read(300).decode(errors="replace")
        if exc.code == 429 or exc.code >= 500:
            raise ChannelError(f"Twilio {exc.code}") from exc
        raise PermanentChannelError(f"Twilio rejected the request ({exc.code}): {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ChannelError(f"Twilio unreachable: {type(exc).__name__}") from exc


def send_sms(to: str, body: str, status_callback: str = "") -> str:
    fields = {"To": to, "From": settings.TWILIO_FROM_NUMBER, "Body": body}
    if status_callback:
        fields["StatusCallback"] = status_callback
    result = _post("Messages", fields)
    return str(result["sid"])


def start_call(to: str, twiml: str, status_callback: str) -> str:
    result = _post(
        "Calls",
        {
            "To": to,
            "From": settings.TWILIO_FROM_NUMBER,
            "Twiml": twiml,
            "StatusCallback": status_callback,
            "StatusCallbackMethod": "POST",
        },
    )
    return str(result["sid"])


def request_signature(url: str, params: Mapping[str, str], auth_token: str) -> str:
    """Twilio's X-Twilio-Signature: base64(HMAC-SHA1(token, url + sorted key/value pairs))."""
    data = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    digest = hmac.new(auth_token.encode(), data.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def valid_signature(url: str, params: Mapping[str, str], signature: str) -> bool:
    if not settings.TWILIO_AUTH_TOKEN or not signature:
        return False
    expected = request_signature(url, params, settings.TWILIO_AUTH_TOKEN)
    return hmac.compare_digest(expected.encode(), signature.encode())
