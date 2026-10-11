"""Delivery channels. Each is a class with one method, `send(notification)`.

Raising `ChannelError` means "transient, retry with backoff"; `PermanentChannelError` means "this
can never succeed" (not configured, number not verified, URL refused) and fails the notification
at once, visibly, instead of burning five retries.
"""

import hashlib
import hmac
import json
import time
from typing import Protocol

from django.conf import settings
from django.core.mail import send_mail

from apps.core import safe_http
from apps.core.text import one_line

from . import links, messages, providers
from .errors import ChannelError, PermanentChannelError
from .models import ActionLink, Notification, UserContact

__all__ = [
    "CHANNELS",
    "PAGE_CHANNELS",
    "ChannelError",
    "PermanentChannelError",
    "sign_webhook",
    "unavailable_reason",
]


class Channel(Protocol):
    def send(self, notification: Notification) -> None: ...


def _contact(notification: Notification) -> UserContact | None:
    return UserContact.objects.filter(user_id=notification.user_id).first()


class InAppChannel:
    """The Notification row *is* the inbox entry, so delivery is just marking it sent."""

    def send(self, notification: Notification) -> None:
        return None


class EmailChannel:
    def send(self, notification: Notification) -> None:
        incident = notification.incident
        url = f"{settings.FRONTEND_URL}/incidents/{incident.pk}"
        ack = links.url_for(links.issue(notification, ActionLink.Action.ACK))
        resolve = links.url_for(links.issue(notification, ActionLink.Action.RESOLVE))
        try:
            send_mail(
                subject=f"[Pulse] #{incident.number} {one_line(incident.title)}",
                message=(
                    f"You are being paged for incident #{incident.number} on "
                    f"{incident.service.name} ({incident.urgency} urgency).\n\n"
                    f"{incident.title}\n\nOpen it: {url}\n"
                    f"Acknowledge (one tap, expires): {ack}\n"
                    f"Resolve (one tap, expires): {resolve}\n"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[notification.user.email],
            )
        except OSError as exc:  # SMTP / socket failures are transient
            raise ChannelError(str(exc)) from exc


def _verified_phone(notification: Notification) -> str:
    """The number to use, only if it is still the user's verified one (never a stale snapshot)."""
    contact = _contact(notification)
    if not (contact and contact.phone_verified):
        raise PermanentChannelError("no verified phone number")
    if contact.phone_number != notification.destination:
        raise PermanentChannelError("the phone number changed after this page was created")
    return contact.phone_number


def _status_callback() -> str:
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/api/v1/webhooks/twilio/status/"


def _record_provider(notification: Notification, sid: str) -> None:
    notification.provider_id = sid
    notification.provider_status = "queued"
    notification.save(update_fields=["provider_id", "provider_status", "updated_at"])


class SmsChannel:
    def send(self, notification: Notification) -> None:
        to = _verified_phone(notification)
        incident = notification.incident
        ack = links.url_for(links.issue(notification, ActionLink.Action.ACK))
        body = messages.sms_text(
            incident.number, incident.service.name, incident.title, incident.urgency, ack
        )
        _record_provider(notification, providers.send_sms(to, body, _status_callback()))


class VoiceChannel:
    def send(self, notification: Notification) -> None:
        to = _verified_phone(notification)
        incident = notification.incident
        token = links.issue(notification, ActionLink.Action.ACK)
        gather = f"{settings.PUBLIC_BASE_URL.rstrip('/')}/api/v1/webhooks/twilio/voice/{token}/"
        twiml = messages.voice_twiml(incident.number, incident.service.name, incident.title, gather)
        _record_provider(notification, providers.start_call(to, twiml, _status_callback()))


def sign_webhook(secret: str, timestamp: str, body: bytes) -> str:
    """`v1=` + hex HMAC-SHA256(secret, "<timestamp>.<body>"). Receivers recompute and compare,
    and should reject timestamps older than a few minutes to stop replays."""
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return "v1=" + mac.hexdigest()


class WebhookChannel:
    """A signed JSON POST to the user's own URL (Slack/Teams incoming webhook, or anything)."""

    def send(self, notification: Notification) -> None:
        contact = _contact(notification)
        if not (contact and contact.webhook_url and contact.webhook_secret):
            raise PermanentChannelError("no webhook configured")
        ack = links.url_for(links.issue(notification, ActionLink.Action.ACK))
        resolve = links.url_for(links.issue(notification, ActionLink.Action.RESOLVE))
        body = json.dumps(
            messages.webhook_payload(notification, ack, resolve), separators=(",", ":")
        ).encode()
        timestamp = str(int(time.time()))
        headers = {
            "X-Pulse-Timestamp": timestamp,
            "X-Pulse-Signature": sign_webhook(contact.webhook_secret, timestamp, body),
            "X-Pulse-Delivery": notification.idempotency_key,
        }
        try:
            response = safe_http.post_bytes(
                contact.webhook_url,
                body,
                headers=headers,
                allow_private=settings.WEBHOOK_ALLOW_PRIVATE,
            )
        except safe_http.UnsafeURL as exc:
            raise PermanentChannelError(f"webhook URL refused: {exc}") from exc
        except safe_http.TransportError as exc:
            raise ChannelError(str(exc)) from exc
        if 200 <= response.status < 300:
            return
        if response.status in (408, 429) or response.status >= 500:
            raise ChannelError(f"webhook answered {response.status}")
        raise PermanentChannelError(f"webhook answered {response.status}")


CHANNELS: dict[str, Channel] = {
    Notification.Channel.IN_APP: InAppChannel(),
    Notification.Channel.EMAIL: EmailChannel(),
    Notification.Channel.SMS: SmsChannel(),
    Notification.Channel.VOICE: VoiceChannel(),
    Notification.Channel.WEBHOOK: WebhookChannel(),
}

# What a person with no personal rules gets: the inbox plus email, immediately.
PAGE_CHANNELS = (Notification.Channel.IN_APP, Notification.Channel.EMAIL)


def unavailable_reason(channel: str, contact: UserContact | None) -> str | None:
    """Why a rule on this channel cannot work right now, or None if it can."""
    if channel in (Notification.Channel.SMS, Notification.Channel.VOICE):
        if not providers.configured():
            return "SMS and voice are not enabled on this server."
        if not (contact and contact.phone_verified):
            return "Verify a phone number first."
    if channel == Notification.Channel.WEBHOOK and not (contact and contact.webhook_url):
        return "Set a webhook URL first."
    return None
