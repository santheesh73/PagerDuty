"""Dispatch Celery work only after the surrounding transaction commits.

Two failure modes this guards against:
1. Enqueue-before-commit: a fast worker reads the row before it exists (or after rollback).
2. Broker down: Redis is disposable, so a failed enqueue is logged, not raised. Postgres
   still holds the truth (`next_escalation_at`, pending Notification rows) and the Beat
   sweepers re-drive anything whose message never arrived.
"""

import logging
from datetime import datetime
from typing import Any

from celery import Task
from django.db import transaction

logger = logging.getLogger(__name__)


def on_commit(task: Task, *args: Any, eta: datetime | None = None, **kwargs: Any) -> None:
    def _send() -> None:
        try:
            options: dict[str, Any] = {"eta": eta} if eta else {}
            task.apply_async(args=args, kwargs=kwargs, **options)
        except Exception:
            logger.exception(
                "enqueue failed; sweeper will recover", extra={"task": task.name, "task_args": args}
            )

    transaction.on_commit(_send)
