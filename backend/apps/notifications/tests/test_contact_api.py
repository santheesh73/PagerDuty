"""Phone verification, webhook setup and personal rules through the API."""

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.notifications.models import NotificationRule, UserContact
from conftest import Paging
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

CONTACT = "/api/v1/me/contact/"
RULES = "/api/v1/me/notification-rules/"


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    cache.clear()


@pytest.fixture
def me(people: Paging) -> APIClient:
    client = APIClient()
    client.force_authenticate(people.on_call)
    return client


def code_sent(twilio) -> str:
    body = twilio.requests[-1].form["Body"]
    return body.split("code: ")[1][:6]


# --- phone --------------------------------------------------------------------------------------


def test_contact_starts_empty(me: APIClient) -> None:
    body = me.get(CONTACT).json()
    assert body["phone_number"] == ""
    assert body["phone_verified"] is False
    assert body["has_webhook"] is False


@pytest.mark.parametrize(
    "number", ["4155550123", "+0123456", "+1 (415) 555-0123", "++14155550123", "abc"]
)
def test_phone_numbers_must_be_e164(me: APIClient, number: str) -> None:
    assert me.patch(CONTACT, {"phone_number": number}, format="json").status_code == 422


def test_the_full_verification_flow(me: APIClient, twilio, people: Paging) -> None:
    assert me.patch(CONTACT, {"phone_number": "+14155550123"}, format="json").status_code == 200
    assert me.post(CONTACT + "phone/send-code/").status_code == 204
    code = code_sent(twilio)
    assert len(code) == 6

    contact = UserContact.objects.get(user=people.on_call)
    assert code not in contact.phone_code_hash, "only a keyed hash of the code is stored"
    assert contact.phone_verified_at is None

    wrong = "000000" if code != "000000" else "111111"
    assert me.post(CONTACT + "phone/verify/", {"code": wrong}, format="json").status_code == 422
    done = me.post(CONTACT + "phone/verify/", {"code": code}, format="json")
    assert done.status_code == 200
    assert done.json()["phone_verified"] is True
    assert (
        me.post(CONTACT + "phone/verify/", {"code": code}, format="json").status_code == 422
    )  # spent


def test_guessing_is_capped_so_a_six_digit_code_cannot_be_brute_forced(
    me: APIClient, twilio
) -> None:
    me.patch(CONTACT, {"phone_number": "+14155550123"}, format="json")
    me.post(CONTACT + "phone/send-code/")
    code = code_sent(twilio)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert me.post(CONTACT + "phone/verify/", {"code": wrong}, format="json").status_code == 422
    locked = me.post(CONTACT + "phone/verify/", {"code": code}, format="json")
    assert locked.status_code == 422, "after 5 wrong guesses even the right code is refused"
    assert "Too many" in str(locked.json())


def test_the_code_expires(me: APIClient, twilio, people: Paging) -> None:
    me.patch(CONTACT, {"phone_number": "+14155550123"}, format="json")
    me.post(CONTACT + "phone/send-code/")
    code = code_sent(twilio)
    UserContact.objects.filter(user=people.on_call).update(
        phone_code_expires_at=timezone.now() - timedelta(seconds=1)
    )
    assert me.post(CONTACT + "phone/verify/", {"code": code}, format="json").status_code == 422


def test_sending_codes_is_rate_limited(me: APIClient, twilio) -> None:
    me.patch(CONTACT, {"phone_number": "+14155550123"}, format="json")
    codes = [me.post(CONTACT + "phone/send-code/").status_code for _ in range(7)]
    assert codes[:5] == [204] * 5
    assert codes[5] == 429
    assert len(twilio.requests) == 5, "throttled requests must not send an SMS"


def test_sending_a_code_needs_a_number_and_a_configured_server(
    me: APIClient, twilio, settings
) -> None:
    assert me.post(CONTACT + "phone/send-code/").status_code == 422  # no number yet
    settings.TWILIO_ACCOUNT_SID = ""
    me.patch(CONTACT, {"phone_number": "+14155550123"}, format="json")
    assert me.post(CONTACT + "phone/send-code/").status_code == 422
    assert twilio.requests == []


def test_changing_the_number_unverifies_it_and_switches_off_the_rules_that_need_it(
    me: APIClient, people: Paging, contact: UserContact, twilio
) -> None:
    NotificationRule.objects.create(user=people.on_call, channel="sms", position=0)
    NotificationRule.objects.create(user=people.on_call, channel="webhook", position=1)
    body = me.patch(CONTACT, {"phone_number": "+14155559999"}, format="json").json()
    assert body["phone_verified"] is False
    enabled = dict(NotificationRule.objects.values_list("channel", "enabled"))
    assert enabled == {"sms": False, "webhook": True}


def test_other_peoples_contact_data_is_not_reachable(me: APIClient, contact: UserContact) -> None:
    stranger = APIClient()
    stranger.force_authenticate(UserFactory())
    assert stranger.get(CONTACT).json()["phone_number"] == ""


# --- webhook ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://hooks.example.com/x",
        "https://127.0.0.1/x",
        "https://169.254.169.254/latest/meta-data/",
        "https://localhost/x",
        "https://10.0.0.1/x",
        "https://user:pw@hooks.example.com/x",
        "https://hooks.example.com:8443/x",
        "ftp://hooks.example.com/x",
    ],
)
def test_unsafe_webhook_urls_are_refused_when_saved(me: APIClient, url: str) -> None:
    response = me.patch(CONTACT, {"webhook_url": url}, format="json")
    assert response.status_code == 422
    assert not UserContact.objects.filter(webhook_url=url).exists()


def test_the_signing_secret_is_shown_once_and_the_url_is_never_echoed(me: APIClient) -> None:
    url = "https://hooks.invalid/services/T0/B0/very-secret-path"
    first = me.patch(CONTACT, {"webhook_url": url}, format="json").json()
    assert len(first["webhook_secret"]) >= 32
    assert first["webhook_host"] == "hooks.invalid"
    assert "very-secret-path" not in str(first)

    later = me.get(CONTACT).json()
    assert "webhook_secret" not in later
    assert "very-secret-path" not in str(later)

    rotated = me.post(CONTACT + "webhook/rotate-secret/").json()["webhook_secret"]
    assert rotated != first["webhook_secret"]


def test_clearing_the_webhook_disables_its_rules(
    me: APIClient, people: Paging, contact: UserContact
) -> None:
    NotificationRule.objects.create(user=people.on_call, channel="webhook", position=0)
    me.patch(CONTACT, {"webhook_url": ""}, format="json")
    assert not NotificationRule.objects.get(user=people.on_call).enabled


# --- rules --------------------------------------------------------------------------------------


def test_rules_crud_with_automatic_positions(me: APIClient) -> None:
    first = me.post(RULES, {"channel": "email", "delay_minutes": 0}, format="json")
    second = me.post(
        RULES, {"channel": "email", "delay_minutes": 10, "urgency": "high"}, format="json"
    )
    assert (first.status_code, second.status_code) == (201, 201)
    assert [first.json()["position"], second.json()["position"]] == [0, 1]
    assert [r["delay_minutes"] for r in me.get(RULES).json()] == [0, 10]

    patched = me.patch(f"{RULES}{second.json()['id']}/", {"delay_minutes": 3}, format="json")
    assert patched.json()["delay_minutes"] == 3
    assert me.delete(f"{RULES}{first.json()['id']}/").status_code == 204
    assert len(me.get(RULES).json()) == 1


def test_rules_are_validated(me: APIClient) -> None:
    assert me.post(RULES, {"channel": "carrier-pigeon"}, format="json").status_code == 422
    assert (
        me.post(RULES, {"channel": "email", "delay_minutes": 1441}, format="json").status_code
        == 422
    )
    assert (
        me.post(RULES, {"channel": "email", "delay_minutes": -1}, format="json").status_code == 422
    )
    assert me.post(RULES, {"channel": "in_app"}, format="json").status_code == 422


def test_a_rule_needing_an_unavailable_channel_is_refused_with_the_reason(
    me: APIClient, twilio, contact: UserContact, people: Paging
) -> None:
    UserContact.objects.filter(user=people.on_call).update(phone_verified_at=None)
    response = me.post(RULES, {"channel": "sms"}, format="json")
    assert response.status_code == 422
    assert "Verify a phone number" in str(response.json())


def test_sms_rules_are_refused_when_the_server_has_no_twilio(
    me: APIClient, contact: UserContact, settings
) -> None:
    settings.TWILIO_ACCOUNT_SID = ""
    assert me.post(RULES, {"channel": "sms"}, format="json").status_code == 422


def test_there_is_a_limit_on_rules_per_person(me: APIClient) -> None:
    for i in range(10):
        assert (
            me.post(RULES, {"channel": "email", "delay_minutes": i}, format="json").status_code
            == 201
        )
    over = me.post(RULES, {"channel": "email"}, format="json")
    assert over.status_code == 422
    assert over.json()["error"]["code"] == "limit_exceeded"


def test_nobody_can_read_or_change_someone_elses_rules(me: APIClient, people: Paging) -> None:
    mine = me.post(RULES, {"channel": "email"}, format="json").json()["id"]
    stranger = APIClient()
    stranger.force_authenticate(UserFactory())
    assert stranger.get(RULES).json() == []
    assert stranger.get(f"{RULES}{mine}/").status_code == 404
    assert stranger.patch(f"{RULES}{mine}/", {"delay_minutes": 1}, format="json").status_code == 404
    assert stranger.delete(f"{RULES}{mine}/").status_code == 404
    assert NotificationRule.objects.filter(pk=mine).exists()


def test_everything_here_requires_a_login() -> None:
    anonymous = APIClient()
    for path in (CONTACT, RULES, CONTACT + "phone/send-code/", CONTACT + "phone/verify/"):
        assert anonymous.get(path).status_code in (403, 405)
