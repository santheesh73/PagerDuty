"""Operators can see how every page of an incident was delivered, and why one failed.

The failure showed on the timeline as "Could not notify" and in a metric, but the reason
(`last_error`) was in no API response: finding out meant the Django admin or a shell."""

import pytest
from rest_framework.test import APIClient

from apps.notifications.models import Notification
from conftest import Paging, TriggerFn

pytestmark = pytest.mark.django_db


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def test_a_responder_sees_each_page_and_why_one_failed(
    service, trigger: TriggerFn, people: Paging
) -> None:
    incident_id = trigger(service).incident_id
    Notification.objects.filter(incident_id=incident_id, channel="email").update(
        status=Notification.Status.FAILED, attempts=5, last_error="[Errno 111] Connection refused"
    )
    response = client_for(people.responder).get(f"/api/v1/incidents/{incident_id}/notifications/")
    assert response.status_code == 200
    rows = response.json()
    failed = [r for r in rows if r["status"] == "failed"]
    assert failed
    assert failed[0]["last_error"] == "[Errno 111] Connection refused"
    assert failed[0]["attempts"] == 5
    assert {
        "channel",
        "status",
        "attempts",
        "last_error",
        "sent_at",
        "next_attempt_at",
        "user",
    } <= set(rows[0])
    assert "destination" not in rows[0], "no phone numbers or webhook hosts"


def test_a_viewer_cannot_read_delivery_errors(service, trigger: TriggerFn, people: Paging) -> None:
    incident_id = trigger(service).incident_id
    response = client_for(people.viewer).get(f"/api/v1/incidents/{incident_id}/notifications/")
    assert response.status_code == 403
