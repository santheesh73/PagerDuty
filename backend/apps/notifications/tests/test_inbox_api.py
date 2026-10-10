import pytest
from rest_framework.test import APIClient

from apps.incidents.models import Incident
from conftest import Paging

pytestmark = pytest.mark.django_db


def test_inbox_lists_in_app_pages_and_tracks_unread(
    api_client: APIClient, open_incident: Incident, people: Paging
) -> None:
    api_client.force_login(people.on_call)
    inbox = api_client.get("/api/v1/notifications/").json()["results"]
    assert len(inbox) == 1  # the email copy isn't an inbox item
    assert inbox[0]["incident"]["number"] == open_incident.number
    assert api_client.get("/api/v1/notifications/unread-count/").json() == {"count": 1}

    read = api_client.post(f"/api/v1/notifications/{inbox[0]['id']}/read/").json()
    assert read["read_at"] is not None
    assert api_client.get("/api/v1/notifications/?unread=1").json()["results"] == []


def test_read_all(api_client: APIClient, open_incident: Incident, people: Paging) -> None:
    api_client.force_login(people.on_call)
    assert api_client.post("/api/v1/notifications/read-all/").json() == {"count": 2}
    assert api_client.get("/api/v1/notifications/unread-count/").json() == {"count": 0}


def test_you_cannot_read_someone_elses_notification(
    api_client: APIClient, open_incident: Incident, people: Paging
) -> None:
    api_client.force_login(people.on_call)
    pk = api_client.get("/api/v1/notifications/").json()["results"][0]["id"]
    api_client.force_login(people.admin)
    assert api_client.post(f"/api/v1/notifications/{pk}/read/").status_code == 404
