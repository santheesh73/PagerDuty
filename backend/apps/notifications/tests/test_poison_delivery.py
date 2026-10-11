"""A channel failure must always spend an attempt, whatever it raises.

Regression: `deliver` caught only ChannelError, so any other exception escaped before the
`attempts` increment committed. MAX_ATTEMPTS never tripped and `redispatch_stuck` re-drove
the same row every sweep, forever.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.notifications import actions
from apps.notifications.channels import ChannelError
from apps.notifications.models import Notification
from tests.factories import IncidentFactory, UserFactory

pytestmark = pytest.mark.django_db


class Boom:
    """A channel whose failure is NOT a ChannelError (e.g. Django's BadHeaderError)."""

    def __init__(self) -> None:
        self.calls = 0

    def send(self, notification: Notification) -> None:
        self.calls += 1
        raise ValueError("bad header in recipient address")


@pytest.fixture
def pending(monkeypatch):
    incident = IncidentFactory()
    note = Notification.objects.create(
        incident=incident,
        user=UserFactory(),
        channel=Notification.Channel.EMAIL,
        idempotency_key="poison-test",
        status=Notification.Status.PENDING,
    )
    channel = Boom()
    monkeypatch.setitem(actions.CHANNELS, Notification.Channel.EMAIL, channel)
    return note, channel


def test_unexpected_error_still_spends_an_attempt(pending):
    note, _ = pending
    with pytest.raises(ChannelError):
        actions.deliver(note.pk)
    note.refresh_from_db()
    assert note.attempts == 1, "attempt counter rolled back; this row would retry forever"
    assert "ValueError" in note.last_error


def test_unexpected_error_eventually_marks_failed(pending):
    note, channel = pending
    for _ in range(actions.MAX_ATTEMPTS - 1):
        with pytest.raises(ChannelError):
            actions.deliver(note.pk)
    actions.deliver(note.pk)  # final attempt gives up instead of raising
    note.refresh_from_db()
    assert note.status == Notification.Status.FAILED
    assert note.attempts == actions.MAX_ATTEMPTS
    assert channel.calls == actions.MAX_ATTEMPTS


def test_exhausted_row_is_not_redispatched(pending):
    note, _ = pending
    for _ in range(actions.MAX_ATTEMPTS - 1):
        with pytest.raises(ChannelError):
            actions.deliver(note.pk)
    actions.deliver(note.pk)
    Notification.objects.filter(pk=note.pk).update(updated_at=timezone.now() - timedelta(hours=1))
    assert actions.redispatch_stuck() == 0, "poison row was picked up again"
