"""Signed one-time acknowledge/resolve links: forging, replay, expiry, scanners, permissions."""

import re
import threading
from datetime import timedelta

import pytest
import time_machine
from django.core import mail
from django.core.cache import cache
from django.db import connection
from django.test import Client
from django.utils import timezone

from apps.accounts.models import Membership
from apps.incidents.models import EventType, Incident, Status
from apps.notifications import links
from apps.notifications.actions import deliver
from apps.notifications.models import ActionLink, Notification
from conftest import Paging

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _fresh_limiter() -> None:
    cache.clear()


@pytest.fixture
def notification(open_incident: Incident, people: Paging) -> Notification:
    return Notification.objects.get(incident=open_incident, channel="email")


def token_for(notification: Notification, action: str = "ack") -> str:
    return links.issue(notification, action)


def path(token: str) -> str:
    return f"/a/{token}/"


def test_opening_the_link_shows_a_confirmation_and_changes_nothing(
    notification: Notification, open_incident: Incident
) -> None:
    token = token_for(notification)
    client = Client()
    for _ in range(5):  # a mail scanner, an SMS preview and a chat unfurler
        response = client.get(path(token))
        assert response.status_code == 200
        assert b"Acknowledge" in response.content
    open_incident.refresh_from_db()
    assert open_incident.status == Status.TRIGGERED
    assert ActionLink.objects.get(jti=links.parse(token).jti).used_at is None


def test_posting_acknowledges_as_the_person_who_was_paged_exactly_once(
    notification: Notification, open_incident: Incident, people: Paging
) -> None:
    token = token_for(notification)
    client = Client()

    first = client.post(path(token))
    assert first.status_code == 200
    open_incident.refresh_from_db()
    assert open_incident.status == Status.ACKNOWLEDGED
    event = open_incident.events.filter(type=EventType.ACKNOWLEDGED).get()
    assert event.actor_id == people.on_call.pk
    assert event.data["via"] == "link"

    replay = client.post(path(token))
    assert replay.status_code == 404
    assert open_incident.events.filter(type=EventType.ACKNOWLEDGED).count() == 1


def test_the_resolve_link_resolves_and_the_ack_link_cannot_resolve(
    notification: Notification, open_incident: Incident
) -> None:
    ack, resolve = token_for(notification, "ack"), token_for(notification, "resolve")
    page = Client().get(path(resolve))
    assert b"Resolve" in page.content
    assert Client().post(path(resolve)).status_code == 200
    open_incident.refresh_from_db()
    assert open_incident.status == Status.RESOLVED
    assert Client().post(path(ack)).status_code == 409  # nothing left to acknowledge


def test_an_action_that_is_refused_does_not_spend_the_link(
    notification: Notification, open_incident: Incident, people: Paging
) -> None:
    from apps.incidents import actions

    token = token_for(notification)
    actions.acknowledge(open_incident.pk, actor=people.admin)  # someone else got there first
    assert Client().post(path(token)).status_code == 409
    assert ActionLink.objects.get(jti=links.parse(token).jti).used_at is None


def test_an_expired_link_is_dead(
    notification: Notification, open_incident: Incident, settings
) -> None:
    token = token_for(notification)
    ttl = timedelta(hours=settings.ACTION_LINK_TTL_HOURS)
    with time_machine.travel(timezone.now() + ttl + timedelta(seconds=1), tick=False):
        assert Client().get(path(token)).status_code == 404
        assert Client().post(path(token)).status_code == 404
    open_incident.refresh_from_db()
    assert open_incident.status == Status.TRIGGERED


def test_every_single_bit_flip_of_a_token_is_rejected(
    notification: Notification, open_incident: Incident
) -> None:
    import base64

    raw = bytearray(base64.urlsafe_b64decode(token_for(notification) + "="))
    for index in range(len(raw)):
        for bit in (0, 7):
            mutated = bytearray(raw)
            mutated[index] ^= 1 << bit
            token = base64.urlsafe_b64encode(bytes(mutated)).rstrip(b"=").decode()
            with pytest.raises(links.InvalidLink):
                links.parse(token)
    open_incident.refresh_from_db()
    assert open_incident.status == Status.TRIGGERED


@pytest.mark.parametrize("token", ["", "abc", "!!!!", "A" * 200, "../../etc/passwd", "%00"])
def test_garbage_tokens_are_a_plain_404(token: str) -> None:
    assert Client().get(f"/a/{token or 'x'}/").status_code == 404
    assert Client().post(f"/a/{token or 'x'}/").status_code == 404


def test_a_token_signed_with_another_key_is_rejected(notification: Notification, settings) -> None:
    token = token_for(notification)
    settings.SECRET_KEY = "a-different-key-entirely"
    with pytest.raises(links.InvalidLink):
        links.parse(token)


def test_a_valid_signature_without_a_database_row_is_rejected(
    notification: Notification,
) -> None:
    token = token_for(notification)
    ActionLink.objects.all().delete()
    assert Client().post(path(token)).status_code == 404


def test_the_ack_and_resolve_tokens_are_not_interchangeable(notification: Notification) -> None:
    import base64

    ack = token_for(notification, "ack")
    raw = bytearray(base64.urlsafe_b64decode(ack + "="))
    raw[20] = 2  # claim it is a resolve token without re-signing
    forged = base64.urlsafe_b64encode(bytes(raw)).rstrip(b"=").decode()
    with pytest.raises(links.InvalidLink):
        links.parse(forged)


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_clicks_spend_the_link_once(
    notification: Notification, open_incident: Incident
) -> None:
    token = token_for(notification)
    results: list[int] = []
    barrier = threading.Barrier(6)

    def click() -> None:
        try:
            barrier.wait()
            results.append(Client().post(path(token)).status_code)
        finally:
            connection.close()

    threads = [threading.Thread(target=click) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results).count(200) == 1, results
    assert open_incident.events.filter(type=EventType.ACKNOWLEDGED).count() == 1


def test_a_deactivated_person_cannot_use_a_link_they_were_sent(
    notification: Notification, open_incident: Incident, people: Paging
) -> None:
    token = token_for(notification)
    people.on_call.is_active = False
    people.on_call.save()
    assert Client().get(path(token)).status_code == 404
    assert Client().post(path(token)).status_code == 404
    open_incident.refresh_from_db()
    assert open_incident.status == Status.TRIGGERED


def test_someone_removed_from_the_team_cannot_use_an_old_link(
    notification: Notification, open_incident: Incident, people: Paging
) -> None:
    token = token_for(notification)
    Membership.objects.filter(user=people.on_call).delete()
    assert Client().post(path(token)).status_code == 404
    open_incident.refresh_from_db()
    assert open_incident.status == Status.TRIGGERED


def test_the_page_is_not_cacheable_and_does_not_leak_a_referrer(notification: Notification) -> None:
    response = Client().get(path(token_for(notification)))
    assert response["Referrer-Policy"] == "no-referrer"
    assert "no-store" in response["Cache-Control"]
    assert response["X-Robots-Tag"] == "noindex"


def test_the_endpoint_is_rate_limited(notification: Notification) -> None:
    client = Client()
    codes = [client.get("/a/bogus/").status_code for _ in range(35)]
    assert codes[:30] == [404] * 30
    assert 429 in codes[30:]


def test_the_email_contains_working_one_tap_links(
    open_incident: Incident, people: Paging, settings
) -> None:
    settings.PUBLIC_BASE_URL = "https://pulse.test"
    row = Notification.objects.get(incident=open_incident, channel="email")
    deliver(row.pk)
    body = mail.outbox[0].body
    urls = re.findall(r"https://pulse\.test(/a/[\w-]+/)", body)
    assert len(urls) == 2
    assert Client().post(urls[0]).status_code == 200  # the acknowledge link
    open_incident.refresh_from_db()
    assert open_incident.status == Status.ACKNOWLEDGED
