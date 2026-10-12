"""Acknowledging while a delivery settles must not abort with a deadlock.

`_settle` locks the notification row and then records a timeline event, whose foreign key takes a
shared lock on the incident. `acknowledge` locks the incident and then updates the notification
rows of delayed steps. With a plain FOR UPDATE on the incident those two orders crossed and
Postgres killed one side: 5 of 5 forced interleavings returned HTTP 500 for a human's acknowledge
(final audit). FOR NO KEY UPDATE does not conflict with the foreign-key lock.
"""

import threading
import time
from datetime import timedelta
from unittest import mock

import pytest
from django.db import connection

from apps.incidents import actions as incident_actions
from apps.incidents.models import Incident, Status
from apps.notifications import actions as notification_actions
from apps.notifications.models import Notification, NotificationRule
from conftest import T0, Paging, TriggerFn

pytestmark = pytest.mark.django_db(transaction=True)
DUE = T0 + timedelta(minutes=5)


def test_an_acknowledge_during_a_delivery_settle_does_not_deadlock(
    service, trigger: TriggerFn, people: Paging
) -> None:
    NotificationRule.objects.create(
        user=people.on_call, channel="email", position=0, delay_minutes=5
    )
    incident = Incident.objects.get(pk=trigger(service, "deadlock").incident_id)
    delayed = Notification.objects.get(incident=incident, user=people.on_call, channel="email")
    settle_holds_row, ack_holds_incident = threading.Event(), threading.Event()
    real_record = notification_actions.record
    real_transition = incident_actions._transition
    outcome: dict[str, str] = {}

    def settle_record(*args, **kwargs):
        settle_holds_row.set()  # the notification row is locked
        ack_holds_incident.wait(5)
        time.sleep(0.2)  # let the acknowledge reach the notification row
        return real_record(*args, **kwargs)

    def ack_transition(*args, **kwargs):
        ack_holds_incident.set()  # the incident row is locked
        settle_holds_row.wait(5)
        return real_transition(*args, **kwargs)

    def deliverer() -> None:
        try:
            with mock.patch.object(notification_actions, "record", settle_record):
                notification_actions.deliver(delayed.pk, now=DUE)
            outcome["deliver"] = "ok"
        except Exception as exc:
            outcome["deliver"] = type(exc.__cause__ or exc).__name__
        finally:
            connection.close()

    def acker() -> None:
        settle_holds_row.wait(5)
        try:
            with mock.patch.object(incident_actions, "_transition", ack_transition):
                incident_actions.acknowledge(incident.pk, actor=people.on_call, now=DUE)
            outcome["ack"] = "ok"
        except Exception as exc:
            outcome["ack"] = type(exc.__cause__ or exc).__name__
        finally:
            connection.close()

    threads = [threading.Thread(target=deliverer), threading.Thread(target=acker)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert outcome == {"deliver": "ok", "ack": "ok"}
    incident.refresh_from_db()
    assert incident.status == Status.ACKNOWLEDGED
