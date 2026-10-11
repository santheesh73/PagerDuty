"""deliver() must not hold a database lock while it talks to SMTP, and must still send once."""

import threading
import time
from datetime import timedelta
from unittest import mock

import pytest
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from apps.incidents.models import Incident
from apps.notifications.actions import CLAIM_TTL, deliver
from apps.notifications.channels import EmailChannel
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db(transaction=True)


def email_row(incident: Incident) -> Notification:
    return Notification.objects.get(incident=incident, channel="email")


def test_the_email_is_sent_with_no_transaction_open_and_no_row_lock(
    open_incident: Incident,
) -> None:
    row = email_row(open_incident)
    seen: dict[str, object] = {}

    def probe(channel: EmailChannel, notification: Notification) -> None:
        seen["in_atomic_block"] = connection.in_atomic_block

        def try_lock() -> None:
            try:
                with transaction.atomic():
                    Notification.objects.select_for_update(nowait=True).get(pk=row.pk)
                seen["lock_free"] = True
            except DatabaseError:
                seen["lock_free"] = False
            finally:
                connection.close()

        worker = threading.Thread(target=try_lock)
        worker.start()
        worker.join()

    with mock.patch.object(EmailChannel, "send", probe):
        assert deliver(row.pk).status == Notification.Status.SENT

    assert seen == {"in_atomic_block": False, "lock_free": True}


def test_two_workers_delivering_the_same_row_send_exactly_once(open_incident: Incident) -> None:
    row = email_row(open_incident)
    sends: list[int] = []
    gate = threading.Barrier(2)

    def slow_send(channel: EmailChannel, notification: Notification) -> None:
        sends.append(notification.pk)
        time.sleep(0.4)  # long enough for the other worker to arrive mid-send

    def worker() -> None:
        try:
            gate.wait()
            deliver(row.pk)
        finally:
            connection.close()

    with mock.patch.object(EmailChannel, "send", slow_send):
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert sends == [row.pk]
    row.refresh_from_db()
    assert (row.status, row.attempts) == (Notification.Status.SENT, 1)


def test_a_claim_left_by_a_crashed_worker_expires_and_the_page_is_retried(
    open_incident: Incident,
) -> None:
    row = email_row(open_incident)
    Notification.objects.filter(pk=row.pk).update(
        claimed_at=timezone.now() - CLAIM_TTL - timedelta(seconds=1), attempts=1
    )
    assert deliver(row.pk).status == Notification.Status.SENT
    row.refresh_from_db()
    assert row.attempts == 2  # the dead worker's try still counts toward the budget


def test_a_fresh_claim_by_another_worker_is_respected(open_incident: Incident) -> None:
    row = email_row(open_incident)
    Notification.objects.filter(pk=row.pk).update(claimed_at=timezone.now())
    with mock.patch.object(EmailChannel, "send") as send:
        assert deliver(row.pk).status == Notification.Status.PENDING
    send.assert_not_called()
