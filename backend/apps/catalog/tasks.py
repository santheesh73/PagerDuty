from celery import shared_task

from . import actions


@shared_task
def expire_service_modes() -> int:
    return actions.expire_service_modes()
