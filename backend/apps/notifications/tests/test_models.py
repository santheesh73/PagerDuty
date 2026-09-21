import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from apps.incidents.models import Incident
from apps.notifications.models import Notification
from apps.services.models import Service
from apps.users.models import Team

User = get_user_model()


@pytest.fixture
def notif_setup():
    team = Team.objects.create(name="Notif Team", slug="notif-team")
    user = User.objects.create_user(username="notif_user", email="notif@example.com")
    service = Service.objects.create(name="Notif Service", slug="notif-svc", team=team)
    incident = Incident.objects.create(service=service, title="Outage", fingerprint="fp-notif-1")
    return {
        "incident": incident,
        "recipient": user,
    }


@pytest.mark.django_db
def test_notification_creation_and_defaults(notif_setup):
    notif = Notification.objects.create(
        incident=notif_setup["incident"],
        recipient=notif_setup["recipient"],
        dedupe_key="dedupe-key-1",
    )
    assert notif.status == Notification.Status.PENDING
    assert notif.channel == Notification.Channel.EMAIL
    assert notif.attempt_count == 0
    assert notif.sent_at is None
    assert notif.failed_at is None
    assert str(notif) == f"Notification {notif.id} [EMAIL -> notif_user] (PENDING)"


@pytest.mark.django_db
def test_notification_dedupe_key_uniqueness_enforced(notif_setup):
    Notification.objects.create(
        incident=notif_setup["incident"],
        recipient=notif_setup["recipient"],
        dedupe_key="same-key",
    )
    with pytest.raises(IntegrityError):
        Notification.objects.create(
            incident=notif_setup["incident"],
            recipient=notif_setup["recipient"],
            dedupe_key="same-key",
        )
