import abc
import logging
from typing import TYPE_CHECKING

from .exceptions import NotificationDeliveryError

if TYPE_CHECKING:
    from .models import Notification

logger = logging.getLogger(__name__)


class BaseNotificationProvider(abc.ABC):
    """
    Abstract interface for dispatching notifications to external communication channels.
    Decouples incident and escalation domain orchestration from external vendor SDKs.
    """

    @abc.abstractmethod
    def send(self, notification: "Notification") -> bool:
        """
        Dispatches the notification.
        Returns True on successful delivery or raises NotificationDeliveryError on failure.
        """
        raise NotImplementedError


class SimulatedEmailProvider(BaseNotificationProvider):
    """
    In-memory / logging simulated email provider for testing and development.
    Does NOT connect to external SMTP, SendGrid, or external email APIs.
    Provides controllable fault-injection flags for deterministic unit/integration testing.
    """

    # Class-level hook for deterministic test fault injection
    force_failure: bool = False
    fail_for_recipients: set[str] = set()

    def send(self, notification: "Notification") -> bool:
        if self.force_failure or (notification.recipient.username in self.fail_for_recipients):
            logger.warning(
                "SimulatedEmailProvider injected delivery failure for notification %s (recipient=%s)",
                notification.id,
                notification.recipient.username,
            )
            raise NotificationDeliveryError(
                f"Simulated email delivery failed for user {notification.recipient.username}"
            )

        recipient_email = notification.recipient.email or f"{notification.recipient.username}@example.com"
        logger.info(
            "SimulatedEmailProvider sent email to %s: Incident INC-%s: %s (Level %s)",
            recipient_email,
            notification.incident_id,
            notification.incident.title,
            notification.escalation_level.order if notification.escalation_level else "N/A",
        )
        return True


def get_notification_provider(channel: str = "EMAIL") -> BaseNotificationProvider:
    """
    Factory resolving the appropriate notification provider implementation by channel.
    """
    normalized = channel.upper()
    if normalized == "EMAIL":
        return SimulatedEmailProvider()
    raise ValueError(f"Unsupported notification channel: {channel}")
