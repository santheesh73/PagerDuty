"""Dispatch Celery work only after the surrounding transaction commits.

Two failure modes this guards against:
1. Enqueue-before-commit: a fast worker reads the row before it exists (or after rollback).
2. Broker down: Redis is disposable, so a failed enqueue is logged, not raised. Postgres
   still holds the truth (`next_escalation_at`, pending Notification rows) and the Beat
   sweepers re-drive anything whose message never arrived.

In demo mode (`TASKS_INLINE`) there is no broker and no worker: work that is due now runs
in-process after commit, once, and anything due later or that fails is left in Postgres for
`/internal/tick/` to drive, exactly as a lost message is in a full deployment.
"""

import logging
from datetime import datetime
from typing import Any

from celery import Task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def on_commit(task: Task, *args: Any, eta: datetime | None = None, **kwargs: Any) -> None:
    def _send() -> None:
        if settings.TASKS_INLINE:
            _run_inline(task, args, kwargs, eta)
            return
        try:
            options: dict[str, Any] = {"eta": eta} if eta else {}
            task.apply_async(args=args, kwargs=kwargs, **options)
        except Exception:
            logger.exception(
                "enqueue failed; sweeper will recover", extra={"task": task.name, "task_args": args}
            )

    transaction.on_commit(_send)


def _run_inline(task: Task, args: tuple, kwargs: dict, eta: datetime | None) -> None:
    if eta is not None and eta > timezone.now():
        return  # not due yet: the tick's sweep runs it when it is
    try:
        # Called directly, a Celery task runs once: its retry re-raises instead of re-queueing.
        task(*args, **kwargs)
    except Exception:
        logger.exception(
            "inline task failed; the tick will retry",
            extra={"task": task.name, "task_args": args},
        )
