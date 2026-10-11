"""What a page says on each channel.

SMS is held to one 160-character GSM-7 segment: a single non-GSM character (an emoji, a smart
quote) silently switches the whole message to UCS-2 and a 70-character limit, and a second
segment costs money and may arrive out of order. So text is reduced to plain printable ASCII
minus the GSM "extension" characters (which cost two septets each), and the title is truncated
to leave room for the acknowledge link, which is never cut.
"""

import re
import unicodedata
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from django.conf import settings

from apps.core.text import one_line

SMS_LIMIT = 160
_GSM_EXTENSION = set("^{}\\[~]|€")
_SPACE = re.compile(r"\s+")


def plain(text: str) -> str:
    """Fold to printable ASCII a single GSM-7 segment can carry."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    folded = "".join(" " if c in _GSM_EXTENSION or not c.isprintable() else c for c in folded)
    return _SPACE.sub(" ", folded).strip()


def sms_text(number: int, service: str, title: str, urgency: str, ack_url: str) -> str:
    tail = f" Ack: {ack_url}"
    head = f"Pulse #{number} {'HIGH' if urgency == 'high' else 'low'} {plain(service)}: "
    room = SMS_LIMIT - len(tail) - len(head)
    title = plain(one_line(title))
    if len(title) > room:
        title = title[: max(room - 3, 0)].rstrip() + "..."
    return (head + title + tail)[:SMS_LIMIT] if room > 0 else (head + tail)[:SMS_LIMIT]


def voice_twiml(number: int, service: str, title: str, gather_url: str) -> str:
    spoken = escape(
        f"Pulse alert. Incident {number}. {plain(service)}. {plain(one_line(title))[:200]}."
    )
    return (
        "<Response>"
        '<Gather input="dtmf" numDigits="1" timeout="10" method="POST" '
        f"action={quoteattr(gather_url)}>"
        f"<Say>{spoken} Press 1 to acknowledge.</Say>"
        "</Gather>"
        "<Say>No response. Goodbye.</Say>"
        "</Response>"
    )


def webhook_payload(notification: Any, ack_url: str, resolve_url: str) -> dict[str, Any]:
    incident = notification.incident
    text = (
        f"Pulse #{incident.number} ({incident.urgency}) {incident.service.name}: "
        f"{one_line(incident.title)}"
    )
    return {
        "text": text,  # Slack incoming webhooks and Teams workflow webhooks both read this
        "incident": {
            "id": incident.pk,
            "number": incident.number,
            "title": one_line(incident.title),
            "urgency": incident.urgency,
            "status": incident.status,
            "service": incident.service.name,
            "url": f"{settings.FRONTEND_URL}/incidents/{incident.pk}",
        },
        "acknowledge_url": ack_url,
        "resolve_url": resolve_url,
        "delivery_id": notification.idempotency_key,
    }
