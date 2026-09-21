from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.incidents.models import Incident
from apps.notifications.models import Notification
from apps.services.models import Service
from apps.users.models import Team

User = get_user_model()


@pytest.fixture
def api_notif():
    client = APIClient()
    team = Team.objects.create(name="API Team", slug="api-team")
    user = User.objects.create_user(username="api_user", email="api_user@example.com")
    service = Service.objects.create(name="API Service", slug="api-svc", team=team)
    incident = Incident.objects.create(service=service, title="API Incident", fingerprint="fp-api-notif")
    notif = Notification.objects.create(
        incident=incident,
        recipient=user,
        dedupe_key="api-notif-key-1",
        status=Notification.Status.FAILED,
        last_error="Temporary SMTP simulation failure",
    )
    return {
        "client": client,
        "notif": notif,
        "incident": incident,
        "user": user,
    }


@pytest.mark.django_db
def test_list_and_retrieve_notifications(api_notif):
    client = api_notif["client"]
    resp = client.get("/api/notifications/")
    assert resp.status_code == 200
    assert len(resp.data) >= 1

    detail_resp = client.get(f"/api/notifications/{api_notif['notif'].id}/")
    assert detail_resp.status_code == 200
    assert detail_resp.data["recipient_username"] == "api_user"
    assert detail_resp.data["status"] == "FAILED"


@pytest.mark.django_db
def test_post_notification_rejected_not_allowed(api_notif):
    client = api_notif["client"]
    resp = client.post("/api/notifications/", {"recipient": api_notif["user"].id}, format="json")
    # Read-only ViewSet: POST not allowed
    assert resp.status_code in (405, 403)


@pytest.mark.django_db(transaction=True)
def test_manual_retry_action_re_enqueues_failed_notification(api_notif):
    client = api_notif["client"]
    notif = api_notif["notif"]

    with patch("apps.notifications.tasks.dispatch_notification.delay") as mock_dispatch:
        resp = client.post(f"/api/notifications/{notif.id}/retry/")
        assert resp.status_code == 200
        assert resp.data["id"] == notif.id
        mock_dispatch.assert_called_once_with(notif.id)

    notif.refresh_from_db()
    assert notif.status == Notification.Status.PENDING


@pytest.mark.django_db
def test_manual_retry_action_rejects_non_failed_notification(api_notif):
    client = api_notif["client"]
    notif = api_notif["notif"]
    notif.status = Notification.Status.SENT
    notif.save()

    resp = client.post(f"/api/notifications/{notif.id}/retry/")
    assert resp.status_code == 400
    assert "Only FAILED notifications" in resp.data["detail"]
