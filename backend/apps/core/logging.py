"""Request-ID propagation: HTTP request -> log lines -> Celery task headers -> worker logs.

One ID follows an alert from the Events API call through the escalation and notification
tasks it triggers, so a single grep reconstructs the whole path.
"""

import logging
import uuid
from contextvars import ContextVar
from typing import Any

from celery.signals import before_task_publish, task_postrun, task_prerun

REQUEST_ID_HEADER = "X-Request-ID"
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return _request_id.get()


def set_request_id(value: str | None) -> Any:
    return _request_id.set(value)


def reset_request_id(token: Any) -> None:
    _request_id.reset(token)


def new_request_id() -> str:
    return uuid.uuid4().hex


class RequestIDFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class RedactRequestFilter(logging.Filter):
    """Django attaches the whole request to `django.request` records; its repr includes the
    query string, which can carry keys. The message already names the path, so drop it."""

    def filter(self, record: logging.LogRecord) -> bool:
        if hasattr(record, "request"):
            record.request = None
        return True


@before_task_publish.connect
def _attach_request_id(headers: dict | None = None, **_: Any) -> None:
    if headers is not None and (rid := get_request_id()):
        headers.setdefault("request_id", rid)


@task_prerun.connect
def _restore_request_id(task: Any = None, **_: Any) -> None:
    rid = getattr(task.request, "request_id", None) if task else None
    set_request_id(rid or new_request_id())


@task_postrun.connect
def _clear_request_id(**_: Any) -> None:
    set_request_id(None)
