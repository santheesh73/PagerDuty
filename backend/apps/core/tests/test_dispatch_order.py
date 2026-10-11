"""Side effects must never run before the transaction that justified them has committed.

If a task is enqueued first, a fast worker can read a row that does not exist yet, or page for a
change that is about to roll back."""

from unittest import mock

import pytest
from django.db import transaction

from apps.escalations.tasks import escalate_incident
from apps.notifications.tasks import deliver_notification
from conftest import TriggerFn

pytestmark = pytest.mark.django_db


def test_tasks_are_enqueued_only_after_commit(
    service, trigger: TriggerFn, django_capture_on_commit_callbacks
) -> None:
    with (
        mock.patch.object(deliver_notification, "apply_async") as deliver_async,
        mock.patch.object(escalate_incident, "apply_async") as escalate_async,
    ):
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            trigger(service)

        # The incident, its pages and its timer exist, but nothing has been handed to the broker.
        deliver_async.assert_not_called()
        escalate_async.assert_not_called()
        assert callbacks, "nothing was registered to run on commit"

        for callback in callbacks:
            callback()  # "commit"
        assert deliver_async.called
        assert escalate_async.called


def test_a_rolled_back_transaction_enqueues_nothing(
    service, trigger: TriggerFn, django_capture_on_commit_callbacks
) -> None:
    def trigger_then_fail() -> None:
        with transaction.atomic():
            trigger(service)
            raise RuntimeError("boom after the pages were decided")

    with (
        mock.patch.object(deliver_notification, "apply_async") as deliver_async,
        mock.patch.object(escalate_incident, "apply_async") as escalate_async,
        django_capture_on_commit_callbacks(execute=False) as callbacks,
        pytest.raises(RuntimeError),
    ):
        trigger_then_fail()

    assert callbacks == []
    deliver_async.assert_not_called()
    escalate_async.assert_not_called()
