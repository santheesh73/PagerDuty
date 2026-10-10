# Import the Celery app on Django start-up so @shared_task binds to it and
# transaction.on_commit dispatch works from web processes as well as workers.
from .celery import app as celery_app

__all__ = ("celery_app",)
