"""Twilio's inbound webhooks: signature-verified, idempotent, order-independent."""

import pytest
from django.test import Client

from apps.incidents.models import EventType, Incident, Status
from apps.notifications import links, providers
from apps.notifications.actions import deliver, page
from apps.notifications.models import Notification, NotificationRule, UserContact
from conftest import T0, Paging

pytestmark = pytest.mark.django_db

STATUS_URL = "/api/v1/webhooks/twilio/status/"


def signed_post(
    path: str, params: dict[str, str], *, token: str | None = None, url: str | None = None
):
    token = token if token is not None else "twilio-test-token"
    full = url or f"https://pulse.test{path}"
    signature = providers.request_signature(full, params, token)
    return Client().post(path, params, HTTP_X_TWILIO_SIGNATURE=signature)


@pytest.fixture
def sent_sms(open_incident: Incident, people: Paging, contact: UserContact, twilio) -> Notification:
    Notification.objects.filter(incident=open_incident).delete()
    NotificationRule.objects.create(user=people.on_call, channel="sms", position=0)
    page(open_incident, [people.on_call], level=0, loop=0, seq=1, now=T0)
    row = Notification.objects.get(incident=open_incident, channel="sms")
    done = deliver(row.pk)
    assert done is not None
    return done


def receipt(notification: Notification, state: str) -> dict[str, str]:
    return {"MessageSid": notification.provider_id, "MessageStatus": state, "To": "+14155550123"}


# --- delivery receipts --------------------------------------------------------------------------


def test_a_signed_receipt_updates_the_notification(sent_sms: Notification) -> None:
    response = signed_post(STATUS_URL, receipt(sent_sms, "delivered"))
    assert response.status_code == 204
    sent_sms.refresh_from_db()
    assert sent_sms.provider_status == "delivered"
    assert sent_sms.delivered_at is not None


def test_replaying_the_same_receipt_changes_nothing(sent_sms: Notification) -> None:
    signed_post(STATUS_URL, receipt(sent_sms, "delivered"))
    sent_sms.refresh_from_db()
    stamp = (sent_sms.delivered_at, sent_sms.updated_at)
    for _ in range(3):
        assert signed_post(STATUS_URL, receipt(sent_sms, "delivered")).status_code == 204
    sent_sms.refresh_from_db()
    assert (sent_sms.delivered_at, sent_sms.updated_at) == stamp


def test_receipts_arriving_out_of_order_never_move_the_state_backwards(
    sent_sms: Notification,
) -> None:
    signed_post(STATUS_URL, receipt(sent_sms, "delivered"))
    signed_post(STATUS_URL, receipt(sent_sms, "sent"))  # late
    signed_post(STATUS_URL, receipt(sent_sms, "queued"))  # later still
    sent_sms.refresh_from_db()
    assert sent_sms.provider_status == "delivered"


def test_a_carrier_failure_is_recorded_on_the_timeline_once(
    sent_sms: Notification, open_incident: Incident
) -> None:
    for _ in range(3):
        signed_post(STATUS_URL, receipt(sent_sms, "undelivered"))
    sent_sms.refresh_from_db()
    assert sent_sms.provider_status == "undelivered"
    failures = open_incident.events.filter(type=EventType.NOTIFICATION_FAILED)
    assert failures.filter(data__channel="sms").count() == 1


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda p: {**p, "MessageStatus": "failed"}, id="params-changed-after-signing"),
        pytest.param(lambda p: {**p, "Extra": "1"}, id="param-added"),
    ],
)
def test_a_tampered_receipt_is_rejected(sent_sms: Notification, mutate) -> None:
    params = receipt(sent_sms, "delivered")
    signature = providers.request_signature(
        f"https://pulse.test{STATUS_URL}", params, "twilio-test-token"
    )
    response = Client().post(STATUS_URL, mutate(params), HTTP_X_TWILIO_SIGNATURE=signature)
    assert response.status_code == 403
    sent_sms.refresh_from_db()
    assert sent_sms.provider_status == "queued"


def test_wrong_missing_and_misaddressed_signatures_are_rejected(sent_sms: Notification) -> None:
    params = receipt(sent_sms, "delivered")
    assert signed_post(STATUS_URL, params, token="not-the-token").status_code == 403
    assert Client().post(STATUS_URL, params).status_code == 403  # no signature at all
    wrong_url = signed_post(
        STATUS_URL, params, url="https://evil.test/api/v1/webhooks/twilio/status/"
    )
    assert wrong_url.status_code == 403
    sent_sms.refresh_from_db()
    assert sent_sms.provider_status == "queued"


def test_the_webhooks_do_not_exist_until_twilio_is_configured(
    sent_sms: Notification, settings
) -> None:
    settings.TWILIO_AUTH_TOKEN = ""
    assert Client().post(STATUS_URL, receipt(sent_sms, "delivered")).status_code == 404


def test_a_receipt_for_an_unknown_message_is_accepted_and_ignored(sent_sms: Notification) -> None:
    response = signed_post(STATUS_URL, {"MessageSid": "SMnope", "MessageStatus": "delivered"})
    assert response.status_code == 204


def test_get_is_not_allowed(sent_sms: Notification) -> None:
    assert Client().get(STATUS_URL).status_code == 405


# --- press 1 to acknowledge ---------------------------------------------------------------------


@pytest.fixture
def voice(open_incident: Incident, people: Paging, contact: UserContact, twilio):
    Notification.objects.filter(incident=open_incident).delete()
    NotificationRule.objects.create(user=people.on_call, channel="voice", position=0)
    page(open_incident, [people.on_call], level=0, loop=0, seq=1, now=T0)
    row = Notification.objects.get(incident=open_incident, channel="voice")
    deliver(row.pk)
    import re

    gather = re.search(r'action="([^"]+)"', twilio.requests[0].form["Twiml"])
    assert gather is not None
    return gather.group(1).removeprefix("https://pulse.test")


def test_pressing_one_acknowledges_the_incident_as_the_person_called(
    voice: str, open_incident: Incident, people: Paging
) -> None:
    response = signed_post(voice, {"Digits": "1", "CallSid": "CA1"})
    assert response.status_code == 200
    assert b"Acknowledged" in response.content
    open_incident.refresh_from_db()
    assert open_incident.status == Status.ACKNOWLEDGED
    event = open_incident.events.filter(type=EventType.ACKNOWLEDGED).get()
    assert event.actor_id == people.on_call.pk
    assert event.data["via"] == "voice"


def test_replaying_the_keypress_does_not_acknowledge_twice(
    voice: str, open_incident: Incident
) -> None:
    signed_post(voice, {"Digits": "1", "CallSid": "CA1"})
    again = signed_post(voice, {"Digits": "1", "CallSid": "CA1"})
    assert b"already handled" in again.content
    assert open_incident.events.filter(type=EventType.ACKNOWLEDGED).count() == 1


def test_any_other_key_acknowledges_nothing(voice: str, open_incident: Incident) -> None:
    response = signed_post(voice, {"Digits": "2", "CallSid": "CA1"})
    assert b"Not acknowledged" in response.content
    open_incident.refresh_from_db()
    assert open_incident.status == Status.TRIGGERED


def test_an_unsigned_keypress_is_rejected(voice: str, open_incident: Incident) -> None:
    assert Client().post(voice, {"Digits": "1"}).status_code == 403
    open_incident.refresh_from_db()
    assert open_incident.status == Status.TRIGGERED


def test_a_signed_request_with_a_garbage_token_acknowledges_nothing(
    open_incident: Incident, twilio
) -> None:
    path = "/api/v1/webhooks/twilio/voice/garbage/"
    response = signed_post(path, {"Digits": "1"})
    assert response.status_code == 200
    assert b"already handled" in response.content
    open_incident.refresh_from_db()
    assert open_incident.status == Status.TRIGGERED


def test_the_voice_token_is_the_same_single_use_capability_as_the_link(
    voice: str, open_incident: Incident
) -> None:
    token = voice.rstrip("/").rsplit("/", 1)[1]
    assert Client().post(f"/a/{token}/").status_code == 200  # spent via the web link...
    again = signed_post(voice, {"Digits": "1"})  # ...so the keypress finds it used
    assert b"already handled" in again.content
    assert links.parse(token).action == "ack"
