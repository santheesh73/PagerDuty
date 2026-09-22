from unittest.mock import MagicMock, patch

import pytest
from celery.exceptions import Retry

from apps.incidents.models import Incident
from apps.notifications.models import Notification
from apps.notifications.services import create_notification
from apps.notifications.tasks import dispatch_notification
from apps.services.models import Service
from apps.users.models import Team, User


@pytest.fixture
def notif_setup(db):
    team = Team.objects.create(name="Notif Team", slug="notif-team")
    user = User.objects.create_user(username="notif_user", email="notif@example.com")
    service = Service.objects.create(name="Notif Svc", slug="notif-svc", team=team)
    incident = Incident.objects.create(
        service=service,
        title="Notification test incident",
        severity=Incident.Severity.CRITICAL,
        fingerprint="notif_fp",
    )
    notification = create_notification(
        incident=incident,
        recipient=user,
        channel="EMAIL",
    )
    return {
        "team": team,
        "user": user,
        "service": service,
        "incident": incident,
        "notification": notification,
    }


@pytest.mark.django_db
def test_notification_bounded_retry_fail_fail_success(notif_setup):
    """
    Section 17: Notification Retry Sequence (Fail -> Fail -> Success).
    Attempt 1: Fails with ConnectionError -> re-enqueued.
    Attempt 2: Fails with ConnectionError -> re-enqueued.
    Attempt 3: Succeeds -> status becomes SENT.
    Expected:
    - Exactly 1 Notification database row.
    - attempt_count = 3.
    - status = SENT.
    - sent_at is populated.
    - last_error cleared.
    """
    notif = notif_setup["notification"]

    with patch("apps.notifications.tasks.get_notification_provider") as mock_get_prov:
        mock_provider = MagicMock()
        mock_provider.send.side_effect = [
            ConnectionError("Attempt 1 connection dropped"),
            ConnectionError("Attempt 2 connection reset"),
            None,  # Attempt 3 succeeds
        ]
        mock_get_prov.return_value = mock_provider

        # Attempt 1
        with pytest.raises((Retry, ConnectionError)):
            dispatch_notification(notif.id, retries=0)
        notif.refresh_from_db()
        assert notif.status == Notification.Status.PENDING
        assert notif.attempt_count == 1
        assert "Attempt 1" in notif.last_error

        # Attempt 2
        with pytest.raises((Retry, ConnectionError)):
            dispatch_notification(notif.id, retries=1)
        notif.refresh_from_db()
        assert notif.status == Notification.Status.PENDING
        assert notif.attempt_count == 2
        assert "Attempt 2" in notif.last_error

        # Attempt 3
        res = dispatch_notification(notif.id, retries=2)
        assert res is True
        notif.refresh_from_db()
        assert notif.status == Notification.Status.SENT
        assert notif.attempt_count == 3
        assert notif.sent_at is not None
        assert notif.last_error == ""

    # Verify no duplicate notifications exist
    all_notifs = Notification.objects.filter(incident=notif_setup["incident"])
    assert all_notifs.count() == 1


@pytest.mark.django_db
def test_notification_permanent_failure_exhausts_retries(notif_setup):
    """
    Section 17: Notification Permanent Failure.
    Simulate persistent provider failure exhausting all retries (max_retries=3).
    Expected:
    - Retries stop after max_retries attempts.
    - Notification status set to FAILED.
    - failed_at populated.
    - attempt_count = 4 (initial attempt + 3 retries).
    - No infinite retry loop.
    """
    notif = notif_setup["notification"]

    with patch("apps.notifications.tasks.get_notification_provider") as mock_get_prov:
        mock_provider = MagicMock()
        mock_provider.send.side_effect = RuntimeError("Permanent SMTP rejection")
        mock_get_prov.return_value = mock_provider

        # Initial + retries 0, 1, 2
        for r in range(3):
            with pytest.raises((Retry, RuntimeError)):
                dispatch_notification(notif.id, retries=r)

        # Final attempt (retries=3 == max_retries)
        res = dispatch_notification(notif.id, retries=3)
        assert res is False

        notif.refresh_from_db()
        assert notif.status == Notification.Status.FAILED
        assert notif.attempt_count == 4
        assert notif.failed_at is not None
        assert "Permanent SMTP rejection" in notif.last_error


@pytest.mark.django_db
def test_notification_deduplication_returns_same_row(notif_setup):
    """
    Section 18 & 33: Notification Dedupe.
    Calling create_notification multiple times with identical parameters
    returns the exact same persisted row.
    """
    inc = notif_setup["incident"]
    user = notif_setup["user"]

    n1 = create_notification(incident=inc, recipient=user, channel="EMAIL")
    n2 = create_notification(incident=inc, recipient=user, channel="EMAIL")
    n3 = create_notification(incident=inc, recipient=user, channel="email")  # casing normalization

    assert n1.id == n2.id == n3.id
    assert Notification.objects.filter(incident=inc).count() == 1
