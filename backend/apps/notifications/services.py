import logging
from typing import TYPE_CHECKING, Any

from django.contrib.auth import get_user_model
from django.db import transaction

from .models import Notification

if TYPE_CHECKING:
    from apps.escalation.models import EscalationLevel
    from apps.incidents.models import Incident

User = get_user_model()
logger = logging.getLogger(__name__)


def build_notification_dedupe_key(
    *,
    incident: "Incident",
    recipient: Any,
    escalation_level: "EscalationLevel | None" = None,
    channel: str = "EMAIL",
) -> str:
    """
    Constructs a deterministic idempotency token for notification dispatch.
    Formula: inc:{incident_id}:lvl:{level_id}:gen:{automation_generation}:usr:{recipient_id}:ch:{channel}
    Guarantees that duplicate task attempts or retries cannot spawn duplicate notifications.
    """
    level_token = str(escalation_level.id) if escalation_level else "none"
    generation = getattr(incident, "automation_generation", 1)
    ch = channel.upper()
    return f"inc:{incident.id}:lvl:{level_token}:gen:{generation}:usr:{recipient.id}:ch:{ch}"


def create_notification(
    *,
    incident: "Incident",
    recipient: Any,
    escalation_level: "EscalationLevel | None" = None,
    channel: str = "EMAIL",
) -> Notification:
    """
    Creates or reuses an existing Notification record matching the dedupe key.
    Enforces strict idempotency.
    """
    dedupe_key = build_notification_dedupe_key(
        incident=incident,
        recipient=recipient,
        escalation_level=escalation_level,
        channel=channel,
    )

    with transaction.atomic():
        notification, created = Notification.objects.get_or_create(
            dedupe_key=dedupe_key,
            defaults={
                "incident": incident,
                "recipient": recipient,
                "escalation_level": escalation_level,
                "channel": channel.upper(),
                "status": Notification.Status.PENDING,
            },
        )
        if created:
            logger.info(
                "Created Notification %s for incident INC-%s (recipient=%s, level=%s)",
                notification.id,
                incident.id,
                recipient.username,
                escalation_level.order if escalation_level else "N/A",
            )
        else:
            logger.info(
                "Reused existing Notification %s for incident INC-%s (dedupe_key=%s)",
                notification.id,
                incident.id,
                dedupe_key,
            )
        return notification
