from unittest.mock import patch

import pytest
from celery.exceptions import Retry
from django.contrib.auth import get_user_model

from apps.incidents.models import Incident
from apps.notifications.models import Notification
from apps.notifications.providers import SimulatedEmailProvider
from apps.notifications.tasks import dispatch_notification
from apps.services.models import Service
from apps.users.models import Team

User = get_user_model()


@pytest.fixture
def task_notif():
    team = Team.objects.create(name="Task Team", slug="task-team")
    user = User.objects.create_user(username="task_user", email="task@example.com")
    service = Service.objects.create(name="Task Service", slug="task-svc", team=team)
    incident = Incident.objects.create(service=service, title="Task Incident", fingerprint="fp-task-notif")
    return Notification.objects.create(incident=incident, recipient=user, dedupe_key="task-notif-key-1")


@pytest.mark.django_db
def test_dispatch_notification_success(task_notif):
    res = dispatch_notification(task_notif.id)
    assert res is True

    task_notif.refresh_from_db()
    assert task_notif.status == Notification.Status.SENT
    assert task_notif.attempt_count == 1
    assert task_notif.sent_at is not None
    assert task_notif.last_error == ""


@pytest.mark.django_db
def test_dispatch_notification_already_sent_noop(task_notif):
    # First dispatch sends
    dispatch_notification(task_notif.id)
    task_notif.refresh_from_db()
    first_sent_at = task_notif.sent_at

    # Second dispatch is idempotent NO-OP
    res = dispatch_notification(task_notif.id)
    assert res is True

    task_notif.refresh_from_db()
    assert task_notif.attempt_count == 1
    assert task_notif.sent_at == first_sent_at


@pytest.mark.django_db
def test_dispatch_notification_retry_on_failure(task_notif):
    SimulatedEmailProvider.force_failure = True
    try:
        # Mock retry to catch and verify it gets triggered
        with patch.object(dispatch_notification, "retry", side_effect=Retry("Simulated Celery Retry")) as mock_retry:
            with pytest.raises(Retry):
                dispatch_notification(task_notif.id)
            mock_retry.assert_called_once()

        task_notif.refresh_from_db()
        assert task_notif.attempt_count == 1
        assert "Simulated email delivery failed" in task_notif.last_error
        assert task_notif.failed_at is not None
    finally:
        SimulatedEmailProvider.force_failure = False


@pytest.mark.django_db
def test_dispatch_notification_marks_failed_when_retries_exhausted(task_notif):
    SimulatedEmailProvider.force_failure = True
    try:
        # Simulate worker when retries have reached max_retries (3)
        res = dispatch_notification(task_notif.id, retries=3)
        assert res is False

        task_notif.refresh_from_db()
        assert task_notif.status == Notification.Status.FAILED
        assert task_notif.attempt_count == 1
        assert "Simulated email delivery failed" in task_notif.last_error
    finally:
        SimulatedEmailProvider.force_failure = False
