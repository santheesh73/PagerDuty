from datetime import timedelta
from unittest import mock

import pytest
from django.core import mail
from django.utils import timezone

from apps.catalog.models import Service
from apps.incidents.models import EventType, Incident
from apps.notifications import actions
from apps.notifications.actions import MAX_ATTEMPTS, deliver, idempotency_key, page
from apps.notifications.channels import ChannelError, EmailChannel
from apps.notifications.models import Notification
from conftest import Paging

pytestmark = pytest.mark.django_db


def email_row(incident: Incident) -> Notification:
    return Notification.objects.get(incident=incident, channel="email")


def test_idempotency_key_format() -> None:
    assert idempotency_key(4, 1, 0, 7, "email") == "incident:4:level:1:loop:0:user:7:channel:email"
    assert idempotency_key(4, 1, 0, 7, "email", seq=99).endswith(":seq:99")


def test_paging_twice_never_double_pages(open_incident: Incident, people: Paging) -> None:
    again = page(open_incident, [people.on_call], level=0, loop=0)
    assert again == []
    assert Notification.objects.filter(incident=open_incident).count() == 2


def test_a_new_sequence_number_is_a_new_page(open_incident: Incident, people: Paging) -> None:
    assert len(page(open_incident, [people.on_call], level=0, loop=0, seq=123)) == 2


def test_delivery_sends_email_and_records_it_on_the_timeline(
    open_incident: Incident, people: Paging
) -> None:
    row = deliver(email_row(open_incident).pk)

    assert row is not None
    assert row.status == Notification.Status.SENT
    assert row.attempts == 1
    assert row.sent_at is not None
    assert [m.to for m in mail.outbox] == [[people.on_call.email]]
    assert f"#{open_incident.number}" in mail.outbox[0].subject
    assert open_incident.events.filter(type=EventType.NOTIFIED).count() == 1


def test_redelivery_of_a_sent_notification_is_a_no_op(open_incident: Incident) -> None:
    pk = email_row(open_incident).pk
    deliver(pk)
    deliver(pk)
    assert len(mail.outbox) == 1


def test_in_app_delivery_marks_sent_without_email(open_incident: Incident) -> None:
    row = Notification.objects.get(incident=open_incident, channel="in_app")
    assert deliver(row.pk).status == Notification.Status.SENT
    assert mail.outbox == []


def test_transient_failures_retry_then_fail_permanently(open_incident: Incident) -> None:
    pk = email_row(open_incident).pk
    with mock.patch.object(EmailChannel, "send", side_effect=ChannelError("smtp down")):
        start = timezone.now()
        for n in range(MAX_ATTEMPTS - 1):  # each retry waits out its delay
            with pytest.raises(ChannelError):
                deliver(pk, now=start + timedelta(hours=n))
            assert Notification.objects.get(pk=pk).status == Notification.Status.PENDING
        final = deliver(pk, now=start + timedelta(hours=MAX_ATTEMPTS))  # last: marked failed

    assert final is not None
    assert (final.status, final.attempts, final.last_error) == ("failed", MAX_ATTEMPTS, "smtp down")
    assert open_incident.events.filter(type=EventType.NOTIFICATION_FAILED).count() == 1


def test_switching_to_debug_after_paging_still_never_sends(open_incident: Incident) -> None:
    Service.objects.filter(pk=open_incident.service_id).update(mode=Service.Mode.DEBUG)
    row = deliver(email_row(open_incident).pk)
    assert row is not None
    assert row.status == Notification.Status.DRY_RUN
    assert mail.outbox == []


def test_sweeper_redispatches_pending_rows_whose_task_was_lost(open_incident: Incident) -> None:
    from apps.notifications.tasks import deliver_notification

    stale = timezone.now() + actions.STUCK_AFTER + timedelta(seconds=1)
    with mock.patch.object(deliver_notification, "delay") as delay:
        assert actions.redispatch_stuck(now=timezone.now()) == 0  # too fresh to be "stuck"
        assert actions.redispatch_stuck(now=stale) == 2
    assert delay.call_count == 2


def test_mark_read_and_mark_all_read(open_incident: Incident, people: Paging) -> None:
    row = Notification.objects.get(incident=open_incident, channel="in_app")
    actions.mark_read(row)
    assert Notification.objects.get(pk=row.pk).read_at is not None
    page(open_incident, [people.on_call], level=0, loop=0, seq=1)
    assert actions.mark_all_read(people.on_call) == 3


def test_a_page_queued_before_resolution_is_never_sent_after_it(open_incident: Incident) -> None:
    """C1: a delayed delivery must not wake someone for a closed incident."""
    from apps.incidents import actions as incident_actions

    pk = email_row(open_incident).pk
    incident_actions.resolve(open_incident.pk, actor=None, via="monitor")

    row = deliver(pk)

    assert row is not None
    assert row.status == Notification.Status.CANCELLED
    assert mail.outbox == []


def test_a_multi_line_summary_still_reaches_the_inbox_by_email(service, trigger) -> None:
    """Alertmanager and Datadog templates emit newlines; a header may not contain one."""
    result = trigger(service, "multi", summary="Disk full\non db-1\r\n(95%)")
    incident = Incident.objects.get(pk=result.incident_id)
    assert incident.title == "Disk full on db-1 (95%)"

    for row in Notification.objects.filter(incident=incident, channel="email"):
        assert deliver(row.pk).status == Notification.Status.SENT
    assert mail.outbox
    assert all("\n" not in m.subject and "\r" not in m.subject for m in mail.outbox)


def test_the_email_subject_is_one_line_even_for_a_title_stored_before_the_fix(
    open_incident: Incident,
) -> None:
    Incident.objects.filter(pk=open_incident.pk).update(title="Legacy\ntitle\twith  gaps")
    row = email_row(open_incident)
    assert deliver(row.pk).status == Notification.Status.SENT
    assert mail.outbox[0].subject == f"[Pulse] #{open_incident.number} Legacy title with gaps"


def test_a_lost_deliver_message_is_redriven_within_three_minutes() -> None:
    """Worst case = a sweep that just missed the row + the sweep interval after STUCK_AFTER."""
    from django.conf import settings

    sweep = settings.CELERY_BEAT_SCHEDULE["sweep-stuck-notifications"]["schedule"]
    assert actions.STUCK_AFTER + sweep <= timedelta(minutes=3)
    assert actions.CLAIM_TTL < actions.STUCK_AFTER  # a dead sender's claim has lapsed by then
