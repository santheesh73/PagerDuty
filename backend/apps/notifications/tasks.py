from celery import shared_task

from . import actions
from .channels import ChannelError


@shared_task(
    acks_late=True,
    autoretry_for=(ChannelError,),
    retry_backoff=actions.RETRY_BASE_SECONDS,  # 30, 60, 120, 240 s (actions.retry_delay)
    retry_backoff_max=600,
    retry_jitter=False,
    # The DB row's `attempts` is the real budget (MAX_ATTEMPTS); this just stops Celery
    # from giving up before the row does.
    max_retries=actions.MAX_ATTEMPTS + 2,
)
def deliver_notification(notification_id: int) -> None:
    actions.deliver(notification_id)


@shared_task
def sweep_stuck_notifications() -> int:
    return actions.redispatch_stuck()
