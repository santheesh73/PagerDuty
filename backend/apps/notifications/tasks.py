from celery import shared_task

from . import actions
from .channels import ChannelError


@shared_task(
    acks_late=True,
    autoretry_for=(ChannelError,),
    retry_backoff=5,
    retry_backoff_max=300,
    retry_jitter=True,
    # The DB row's `attempts` is the real budget (MAX_ATTEMPTS); this just stops Celery
    # from giving up before the row does.
    max_retries=actions.MAX_ATTEMPTS + 2,
)
def deliver_notification(notification_id: int) -> None:
    actions.deliver(notification_id)


@shared_task
def sweep_stuck_notifications() -> int:
    return actions.redispatch_stuck()
