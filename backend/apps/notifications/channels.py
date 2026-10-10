"""Delivery channels. Adding SMS or push is one class implementing `Channel`."""

from typing import Protocol

from django.conf import settings
from django.core.mail import send_mail

from .models import Notification


class ChannelError(Exception):
    """A transient delivery failure; the task retries with backoff."""


class Channel(Protocol):
    def send(self, notification: Notification) -> None: ...


class InAppChannel:
    """The Notification row *is* the inbox entry, so delivery is just marking it sent."""

    def send(self, notification: Notification) -> None:
        return None


class EmailChannel:
    def send(self, notification: Notification) -> None:
        incident = notification.incident
        url = f"{settings.FRONTEND_URL}/incidents/{incident.pk}"
        try:
            send_mail(
                subject=f"[Pulse] #{incident.number} {incident.title}",
                message=(
                    f"You are being paged for incident #{incident.number} on "
                    f"{incident.service.name} ({incident.urgency} urgency).\n\n"
                    f"{incident.title}\n\nAcknowledge: {url}\n"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[notification.user.email],
            )
        except OSError as exc:  # SMTP / socket failures are transient
            raise ChannelError(str(exc)) from exc


CHANNELS: dict[str, Channel] = {
    Notification.Channel.IN_APP: InAppChannel(),
    Notification.Channel.EMAIL: EmailChannel(),
}

# Personal notification rules are a non-goal: every page goes to every channel.
PAGE_CHANNELS = (Notification.Channel.IN_APP, Notification.Channel.EMAIL)
