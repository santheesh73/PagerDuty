"""Personal notification rules: the plan is snapshotted at page time and delayed steps chase an
unanswered page, never an answered or closed one (invariants I18, I19; I13, C1 still hold)."""

from datetime import timedelta
from unittest import mock

import pytest
from django.core.management import call_command

from apps.catalog.models import Service
from apps.core import selfcheck
from apps.incidents import actions as incident_actions
from apps.incidents.models import Incident
from apps.notifications import actions as notification_actions
from apps.notifications.actions import deliver, page, redispatch_stuck
from apps.notifications.models import Notification, NotificationRule, UserContact
from conftest import T0, Paging

pytestmark = pytest.mark.django_db


def make_rule(user, channel, delay=0, position=0, **kw):
    return NotificationRule.objects.create(
        user=user, channel=channel, delay_minutes=delay, position=position, **kw
    )


def fresh_page(incident, user, seq=1):
    Notification.objects.filter(incident=incident).delete()
    return page(incident, [user], level=0, loop=0, seq=seq, now=T0)


def channels_of(incident) -> list[str]:
    return sorted(Notification.objects.filter(incident=incident).values_list("channel", flat=True))


def test_with_no_rules_a_person_gets_the_inbox_and_email_immediately(
    open_incident: Incident, people: Paging
) -> None:
    fresh_page(open_incident, people.on_call)
    assert channels_of(open_incident) == ["email", "in_app"]
    assert (
        Notification.objects.filter(incident=open_incident, not_before__isnull=False).count() == 0
    )


def test_rules_replace_the_default_but_the_inbox_entry_always_exists(
    open_incident: Incident, people: Paging, contact: UserContact, twilio
) -> None:
    make_rule(people.on_call, "sms", delay=0, position=0)
    make_rule(people.on_call, "voice", delay=5, position=1)
    fresh_page(open_incident, people.on_call)

    assert channels_of(open_incident) == ["in_app", "sms", "voice"]  # no email: they chose
    voice = Notification.objects.get(incident=open_incident, channel="voice")
    assert voice.not_before == T0 + timedelta(minutes=5)
    assert voice.status == Notification.Status.PENDING
    assert Notification.objects.get(incident=open_incident, channel="sms").not_before is None


def test_disabled_rules_do_not_count_so_the_default_applies(
    open_incident: Incident, people: Paging, contact: UserContact, twilio
) -> None:
    make_rule(people.on_call, "sms", enabled=False)
    fresh_page(open_incident, people.on_call)
    assert channels_of(open_incident) == ["email", "in_app"]


def test_a_rule_can_be_limited_to_high_or_low_urgency(
    open_incident: Incident, people: Paging, contact: UserContact, twilio
) -> None:
    make_rule(people.on_call, "voice", position=0, urgency="high")
    make_rule(people.on_call, "sms", position=1, urgency="low")
    assert open_incident.urgency == "high"
    fresh_page(open_incident, people.on_call)
    assert channels_of(open_incident) == ["in_app", "voice"]


def test_the_same_channel_can_appear_twice_in_one_plan(
    open_incident: Incident, people: Paging, contact: UserContact, twilio
) -> None:
    make_rule(people.on_call, "sms", delay=0, position=0)
    make_rule(people.on_call, "sms", delay=10, position=1)
    fresh_page(open_incident, people.on_call)
    assert channels_of(open_incident) == ["in_app", "sms", "sms"]


# --- delayed steps ------------------------------------------------------------------------------


def delayed_sms(incident, people):
    make_rule(people.on_call, "sms", delay=5)
    fresh_page(incident, people.on_call)
    return Notification.objects.get(incident=incident, channel="sms")


def test_a_delayed_step_is_not_sent_early_and_is_sent_once_due(
    open_incident: Incident, people: Paging, contact: UserContact, twilio
) -> None:
    step = delayed_sms(open_incident, people)

    early = deliver(step.pk, now=T0 + timedelta(minutes=4, seconds=59))
    assert early is not None
    assert early.status == Notification.Status.PENDING
    assert early.attempts == 0, "an early or duplicate task must not even count as an attempt"
    assert twilio.requests == []

    on_time = deliver(step.pk, now=T0 + timedelta(minutes=5))
    assert on_time is not None
    assert on_time.status == Notification.Status.SENT
    assert len(twilio.requests) == 1


def test_acknowledging_cancels_the_later_steps_but_not_the_ones_already_due(
    open_incident: Incident, people: Paging, contact: UserContact, twilio
) -> None:
    step = delayed_sms(open_incident, people)
    incident_actions.acknowledge(
        open_incident.pk, actor=people.responder, now=T0 + timedelta(minutes=1)
    )

    step.refresh_from_db()
    assert step.status == Notification.Status.CANCELLED
    deliver(step.pk, now=T0 + timedelta(minutes=6))
    assert twilio.requests == []


def test_a_late_step_is_cancelled_at_claim_time_even_if_the_ack_missed_it(
    open_incident: Incident, people: Paging, contact: UserContact, twilio
) -> None:
    """The acknowledge-time cancel is an optimisation; the claim-time guard is the rule."""
    step = delayed_sms(open_incident, people)
    Incident.objects.filter(pk=open_incident.pk).update(status="acknowledged")

    done = deliver(step.pk, now=T0 + timedelta(minutes=6))

    assert done is not None
    assert done.status == Notification.Status.CANCELLED
    assert twilio.requests == []


def test_resolving_cancels_a_pending_step_too(
    open_incident: Incident, people: Paging, contact: UserContact, twilio
) -> None:
    step = delayed_sms(open_incident, people)
    incident_actions.resolve(
        open_incident.pk, actor=people.responder, now=T0 + timedelta(minutes=1)
    )
    done = deliver(step.pk, now=T0 + timedelta(minutes=6))
    assert done is not None
    assert done.status == Notification.Status.CANCELLED
    assert twilio.requests == []


def test_an_unacknowledge_pages_the_plan_again_from_the_start(
    open_incident: Incident, people: Paging, contact: UserContact, twilio
) -> None:
    make_rule(people.on_call, "sms", delay=5)
    fresh_page(open_incident, people.on_call)
    incident_actions.acknowledge(
        open_incident.pk, actor=people.responder, now=T0 + timedelta(minutes=1)
    )
    incident_actions.unacknowledge(
        open_incident.pk, actor=people.responder, now=T0 + timedelta(minutes=2)
    )

    live = Notification.objects.filter(
        incident=open_incident, channel="sms", status=Notification.Status.PENDING
    )
    assert live.count() == 1
    assert live.get().not_before == T0 + timedelta(minutes=7)


def test_maintenance_incidents_page_nobody_whatever_the_rules(
    open_incident: Incident, people: Paging, contact: UserContact, twilio
) -> None:
    make_rule(people.on_call, "sms")
    Incident.objects.filter(pk=open_incident.pk).update(is_maintenance=True)
    open_incident.refresh_from_db()
    Notification.objects.filter(incident=open_incident).delete()
    assert page(open_incident, [people.on_call], level=0, loop=0, seq=1, now=T0) == []
    assert Notification.objects.filter(incident=open_incident).count() == 0


def test_debug_mode_records_every_step_as_a_dry_run(
    open_incident: Incident, people: Paging, contact: UserContact, twilio
) -> None:
    make_rule(people.on_call, "sms", delay=5)
    Service.objects.filter(pk=open_incident.service_id).update(mode=Service.Mode.DEBUG)
    open_incident.refresh_from_db()
    fresh_page(open_incident, people.on_call)
    assert set(
        Notification.objects.filter(incident=open_incident).values_list("status", flat=True)
    ) == {Notification.Status.DRY_RUN}
    assert twilio.requests == []


# --- the snapshot -------------------------------------------------------------------------------


def test_editing_rules_after_a_page_never_changes_that_page(
    open_incident: Incident, people: Paging, contact: UserContact, twilio
) -> None:
    make_rule(people.on_call, "sms", delay=5)
    fresh_page(open_incident, people.on_call)
    before = list(
        Notification.objects.filter(incident=open_incident)
        .order_by("pk")
        .values_list("pk", "idempotency_key")
    )

    NotificationRule.objects.all().delete()
    make_rule(people.on_call, "voice", delay=0)
    again = page(open_incident, [people.on_call], level=0, loop=0, seq=1, now=T0)

    assert again == [], "the same page must not be re-planned from the new rules"
    after = list(
        Notification.objects.filter(incident=open_incident)
        .order_by("pk")
        .values_list("pk", "idempotency_key")
    )
    assert after == before


def test_each_row_remembers_the_rule_that_made_it(
    open_incident: Incident, people: Paging, contact: UserContact, twilio
) -> None:
    make_rule(people.on_call, "voice", delay=3, position=4)
    fresh_page(open_incident, people.on_call)
    voice = Notification.objects.get(incident=open_incident, channel="voice")
    assert voice.rule_snapshot == {"v": 1, "position": 4, "channel": "voice", "delay_minutes": 3}
    NotificationRule.objects.all().update(delay_minutes=60)
    voice.refresh_from_db()
    assert voice.rule_snapshot["delay_minutes"] == 3


# --- the database is the timer ------------------------------------------------------------------


def test_a_lost_eta_message_is_recovered_by_the_stuck_sweep_once_the_step_is_due(
    open_incident: Incident, people: Paging, contact: UserContact, twilio
) -> None:
    step = delayed_sms(open_incident, people)
    Notification.objects.filter(pk=step.pk).update(updated_at=T0)  # created "at T0"
    with mock.patch("apps.notifications.tasks.deliver_notification.delay") as delay:
        assert redispatch_stuck(now=T0 + timedelta(minutes=4)) == 0, "a future step is not stuck"
        assert redispatch_stuck(now=T0 + timedelta(minutes=5, seconds=100)) >= 1
        assert step.pk in [call.args[0] for call in delay.call_args_list]


def test_selfcheck_does_not_call_a_future_step_stuck(
    open_incident: Incident, people: Paging, contact: UserContact, twilio
) -> None:
    make_rule(people.on_call, "sms", delay=30)
    fresh_page(open_incident, people.on_call)
    later = T0 + timedelta(minutes=20)  # past the 5-minute stuck limit, but the step is not due
    Notification.objects.filter(incident=open_incident).exclude(channel="sms").update(
        status=Notification.Status.SENT
    )
    assert selfcheck.stuck_notifications(later) == 0
    assert selfcheck.stuck_notifications(T0 + timedelta(minutes=37)) == 1


def test_dispatch_is_scheduled_for_the_step_time(
    open_incident: Incident,
    people: Paging,
    contact: UserContact,
    twilio,
    django_capture_on_commit_callbacks,
) -> None:
    make_rule(people.on_call, "sms", delay=5)
    with mock.patch("apps.core.dispatch.on_commit") as dispatch_on_commit:
        fresh_page(open_incident, people.on_call)
    etas = {c.kwargs.get("eta") for c in dispatch_on_commit.call_args_list}
    assert T0 + timedelta(minutes=5) in etas
    assert None in etas


def test_notification_actions_expose_the_step_planner() -> None:
    assert notification_actions.Step("sms", 0, 5).snapshot["delay_minutes"] == 5
    assert notification_actions.Step("email", None).snapshot == {}


def test_manage_selfcheck_still_runs(capsys) -> None:
    call_command("selfcheck", "--no-beat")
    assert "ok   database" in capsys.readouterr().out
