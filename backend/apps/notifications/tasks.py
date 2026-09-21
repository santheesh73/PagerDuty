import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import Notification
from .providers import get_notification_provider

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def dispatch_notification(self, notification_id: int, retries: int | None = None) -> bool:
    """
    Asynchronously delivers a notification record via its configured provider.
    - Idempotent: If notification is already SENT, returns True without re-sending.
    - Bounded retries: Retries on transient failure up to max_retries with backoff.
    - Commits attempt_count and failure details to database before Celery retry.
    """
    should_retry = False
    retry_exc = None

    with transaction.atomic():
        notification = (
            Notification.objects.select_for_update()
            .filter(pk=notification_id)
            .first()
        )
        if not notification:
            logger.warning("dispatch_notification: Notification %s not found.", notification_id)
            return False

        if notification.status == Notification.Status.SENT:
            logger.info("dispatch_notification: Notification %s already SENT. Skipping.", notification_id)
            return True

        notification.attempt_count += 1

        try:
            provider = get_notification_provider(notification.channel)
            provider.send(notification)

            notification.status = Notification.Status.SENT
            notification.sent_at = timezone.now()
            notification.last_error = ""
            notification.save(update_fields=["status", "sent_at", "last_error", "attempt_count", "updated_at"])
            logger.info(
                "Successfully dispatched notification %s to %s",
                notification.id,
                notification.recipient.username,
            )
            return True

        except Exception as exc:
            logger.warning(
                "Delivery attempt %s for notification %s failed: %s",
                notification.attempt_count,
                notification.id,
                exc,
            )
            notification.last_error = str(exc)
            notification.failed_at = timezone.now()

            retries_so_far = retries if retries is not None else getattr(self.request, "retries", 0)
            if retries_so_far < self.max_retries:
                notification.save(update_fields=["last_error", "failed_at", "attempt_count", "updated_at"])
                should_retry = True
                retry_exc = exc
            else:
                notification.status = Notification.Status.FAILED
                notification.save(update_fields=["status", "last_error", "failed_at", "attempt_count", "updated_at"])
                logger.error(
                    "Exhausted retries for notification %s. Marked as FAILED.",
                    notification.id,
                )
                return False

    # Raise retry outside the transaction block so DB changes are committed
    if should_retry and retry_exc:
        raise self.retry(exc=retry_exc)

    return False
