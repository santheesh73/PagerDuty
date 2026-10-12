"""SMS, voice and webhook delivery against fakes: what we send, and how failures are classified."""

import json
import xml.etree.ElementTree as ET
from datetime import timedelta

import pytest
from django.utils import timezone
from hypothesis import given
from hypothesis import strategies as st

from apps.incidents.models import EventType, Incident
from apps.notifications import messages
from apps.notifications.actions import MAX_ATTEMPTS, deliver, page
from apps.notifications.channels import ChannelError, sign_webhook
from apps.notifications.models import Notification, NotificationRule, UserContact
from conftest import Paging

pytestmark = pytest.mark.django_db


def rule(user, channel: str, delay: int = 0, position: int = 0, **kw) -> NotificationRule:
    return NotificationRule.objects.create(
        user=user, channel=channel, delay_minutes=delay, position=position, **kw
    )


def row(incident: Incident, channel: str) -> Notification:
    return Notification.objects.get(incident=incident, channel=channel)


# --- SMS ----------------------------------------------------------------------------------------


def test_sms_goes_to_twilio_with_credentials_a_short_body_and_a_status_callback(
    open_incident: Incident, people: Paging, contact: UserContact, twilio
) -> None:
    Notification.objects.filter(incident=open_incident).delete()
    rule(people.on_call, "sms")
    page(open_incident, [people.on_call], level=0, loop=0, seq=1)

    sms = row(open_incident, "sms")
    assert sms.destination == "+14155550123"
    assert sms.rule_snapshot == {"v": 1, "position": 0, "channel": "sms", "delay_minutes": 0}
    done = deliver(sms.pk)

    assert done is not None
    assert done.status == Notification.Status.SENT
    request = twilio.requests[0]
    assert request.path == "/2010-04-01/Accounts/ACtest/Messages.json"
    assert request.headers["Authorization"].startswith("Basic ")
    assert request.form["To"] == "+14155550123"
    assert request.form["From"] == "+15005550006"
    assert len(request.form["Body"]) <= 160
    assert "https://pulse.test/a/" in request.form["Body"]
    assert request.form["StatusCallback"] == "https://pulse.test/api/v1/webhooks/twilio/status/"
    assert done.provider_id.startswith("SM1-")
    assert done.provider_status == "queued"


@given(
    title=st.text(max_size=400),
    service=st.text(min_size=1, max_size=80),
    number=st.integers(min_value=1, max_value=10**7),
    urgency=st.sampled_from(["high", "low"]),
)
def test_sms_text_is_one_gsm_segment_whatever_the_title_contains(
    title: str, service: str, number: int, urgency: str
) -> None:
    link = "https://pulse.example.com/a/" + "x" * 44 + "/"
    text = messages.sms_text(number, service, title, urgency, link)
    assert len(text) <= 160
    assert text.endswith(f" Ack: {link}"), "the link must never be truncated"
    assert text.isascii()
    assert not set(text) & set("^{}\\[~]|€"), "extension characters cost two septets"
    assert "\n" not in text


def test_sms_text_folds_accents_and_drops_emoji() -> None:
    text = messages.sms_text(
        7, "café-api", "Déploiement \U0001f525 cassé", "high", "https://x/a/t/"
    )
    assert "cafe-api" in text
    assert "Deploiement" in text
    assert "\U0001f525" not in text


# --- voice --------------------------------------------------------------------------------------


def test_voice_call_carries_wellformed_twiml_that_gathers_a_keypress(
    open_incident: Incident, people: Paging, contact: UserContact, twilio
) -> None:
    Notification.objects.filter(incident=open_incident).delete()
    open_incident.title = 'CPU <95%> & "swap" > 90'
    open_incident.save()
    rule(people.on_call, "voice")
    page(open_incident, [people.on_call], level=0, loop=0, seq=1)

    deliver(row(open_incident, "voice").pk)

    request = twilio.requests[0]
    assert request.path == "/2010-04-01/Accounts/ACtest/Calls.json"
    root = ET.fromstring(request.form["Twiml"])  # noqa: S314 - our own TwiML; well-formed despite < > & " in the title
    gather = root.find("Gather")
    assert gather is not None
    assert gather.get("numDigits") == "1"
    assert gather.get("action", "").startswith("https://pulse.test/api/v1/webhooks/twilio/voice/")
    say = (gather.findtext("Say") or "") + ""
    assert "Press 1 to acknowledge" in say
    assert "CPU" in say


# --- failure classification ---------------------------------------------------------------------


def test_a_rejected_number_fails_at_once_instead_of_retrying(
    open_incident: Incident, people: Paging, contact: UserContact, twilio
) -> None:
    twilio.script = [(400, {"code": 21211, "message": "invalid To"})]
    Notification.objects.filter(incident=open_incident).delete()
    rule(people.on_call, "sms")
    page(open_incident, [people.on_call], level=0, loop=0, seq=1)

    done = deliver(row(open_incident, "sms").pk)

    assert done is not None
    assert done.status == Notification.Status.FAILED
    assert done.attempts == 1, "a 4xx will never succeed, so it must not burn retries"
    assert "400" in done.last_error
    assert open_incident.events.filter(type=EventType.NOTIFICATION_FAILED).count() == 1


def test_a_twilio_outage_is_retried_then_given_up_on(
    open_incident: Incident, people: Paging, contact: UserContact, twilio
) -> None:
    twilio.script = [(503, {})]
    Notification.objects.filter(incident=open_incident).delete()
    rule(people.on_call, "sms")
    page(open_incident, [people.on_call], level=0, loop=0, seq=1)
    pk = row(open_incident, "sms").pk

    start = timezone.now()
    for n in range(MAX_ATTEMPTS - 1):  # each retry waits out its delay (actions.retry_delay)
        with pytest.raises(ChannelError):
            deliver(pk, now=start + timedelta(hours=n + 1))
    last = deliver(pk, now=start + timedelta(hours=MAX_ATTEMPTS))
    assert last is not None
    assert last.status == Notification.Status.FAILED
    assert last.attempts == MAX_ATTEMPTS
    assert len(twilio.requests) == MAX_ATTEMPTS


def test_unconfigured_sms_is_recorded_as_failed_when_the_page_is_made(
    open_incident: Incident, people: Paging, contact: UserContact, settings
) -> None:
    settings.TWILIO_ACCOUNT_SID = ""
    Notification.objects.filter(incident=open_incident).delete()
    rule(people.on_call, "sms")
    page(open_incident, [people.on_call], level=0, loop=0, seq=1)

    sms = row(open_incident, "sms")
    assert sms.status == Notification.Status.FAILED
    assert "not enabled" in sms.last_error
    assert open_incident.events.filter(type=EventType.NOTIFICATION_FAILED).exists()


def test_an_unverified_phone_is_recorded_as_failed_not_texted(
    open_incident: Incident, people: Paging, contact: UserContact, twilio
) -> None:
    contact.phone_verified_at = None
    contact.save()
    Notification.objects.filter(incident=open_incident).delete()
    rule(people.on_call, "sms")
    page(open_incident, [people.on_call], level=0, loop=0, seq=1)

    assert row(open_incident, "sms").status == Notification.Status.FAILED
    assert twilio.requests == []


def test_a_number_changed_after_the_page_is_never_used(
    open_incident: Incident, people: Paging, contact: UserContact, twilio
) -> None:
    Notification.objects.filter(incident=open_incident).delete()
    rule(people.on_call, "sms", delay=5)
    page(open_incident, [people.on_call], level=0, loop=0, seq=1)
    contact.phone_number = "+14155559999"  # changed (and re-verified) before the step fires
    contact.save()

    done = deliver(row(open_incident, "sms").pk, now=timezone.now() + timedelta(minutes=6))

    assert done is not None
    assert done.status == Notification.Status.FAILED
    assert "changed" in done.last_error
    assert twilio.requests == []


# --- webhook ------------------------------------------------------------------------------------


def webhook_setup(
    incident: Incident, people: Paging, contact: UserContact, receiver
) -> Notification:
    contact.webhook_url = receiver.url + "/hook"
    contact.save()
    Notification.objects.filter(incident=incident).delete()
    rule(people.on_call, "webhook")
    page(incident, [people.on_call], level=0, loop=0, seq=1)
    return row(incident, "webhook")


def test_webhook_posts_signed_slack_compatible_json(
    open_incident: Incident, people: Paging, contact: UserContact, receiver
) -> None:
    notification = webhook_setup(open_incident, people, contact, receiver)
    assert notification.destination == "127.0.0.1", "only the host is stored, never the secret URL"

    done = deliver(notification.pk)

    assert done is not None
    assert done.status == Notification.Status.SENT
    request = receiver.requests[0]
    assert request.path == "/hook"
    body = json.loads(request.body)
    assert body["text"].startswith(f"Pulse #{open_incident.number}")
    assert body["incident"]["id"] == open_incident.pk
    assert (
        body["acknowledge_url"].startswith("https://pulse.test/a/")
        or "/a/" in body["acknowledge_url"]
    )
    assert body["resolve_url"] != body["acknowledge_url"]
    headers = {k.lower(): v for k, v in request.headers.items()}
    expected = sign_webhook("whsec-test-secret", headers["x-pulse-timestamp"], request.body)
    assert headers["x-pulse-signature"] == expected
    assert headers["x-pulse-delivery"] == notification.idempotency_key


def test_a_tampered_webhook_body_fails_signature_verification(
    open_incident: Incident, people: Paging, contact: UserContact, receiver
) -> None:
    deliver(webhook_setup(open_incident, people, contact, receiver).pk)
    request = receiver.requests[0]
    timestamp = {k.lower(): v for k, v in request.headers.items()}["x-pulse-timestamp"]
    forged = sign_webhook("a-different-secret", timestamp, request.body)
    assert forged != {k.lower(): v for k, v in request.headers.items()}["x-pulse-signature"]
    assert sign_webhook("whsec-test-secret", timestamp, request.body + b" ") != forged


@pytest.mark.parametrize(
    ("status", "terminal"), [(500, False), (429, False), (404, True), (410, True), (302, True)]
)
def test_webhook_status_codes_split_into_retry_and_give_up(
    open_incident: Incident,
    people: Paging,
    contact: UserContact,
    receiver,
    status: int,
    terminal: bool,
) -> None:
    receiver.script = [(status, b"x")]
    notification = webhook_setup(open_incident, people, contact, receiver)
    if terminal:
        done = deliver(notification.pk)
        assert done is not None
        assert done.status == Notification.Status.FAILED
        assert done.attempts == 1
    else:
        with pytest.raises(ChannelError):
            deliver(notification.pk)


def test_a_webhook_aimed_at_an_internal_address_is_refused_and_never_called(
    open_incident: Incident, people: Paging, contact: UserContact, receiver, settings
) -> None:
    notification = webhook_setup(open_incident, people, contact, receiver)
    settings.WEBHOOK_ALLOW_PRIVATE = False  # production behaviour: the receiver is on 127.0.0.1

    done = deliver(notification.pk)

    assert done is not None
    assert done.status == Notification.Status.FAILED
    assert "refused" in done.last_error
    assert receiver.requests == [], "the SSRF guard must stop the request before it is sent"
