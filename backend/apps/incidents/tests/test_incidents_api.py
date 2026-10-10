from datetime import timedelta

import pytest
from rest_framework.test import APIClient

from apps.incidents.models import Incident
from conftest import T0, Paging, TriggerFn
from tests.factories import MembershipFactory, ServiceFactory

pytestmark = pytest.mark.django_db


def url(incident: Incident, action: str = "") -> str:
    return f"/api/v1/incidents/{incident.pk}/" + (f"{action}/" if action else "")


def test_list_shows_only_incidents_from_your_teams(
    api_client: APIClient, open_incident: Incident, people: Paging, trigger: TriggerFn
) -> None:
    trigger(ServiceFactory(), "elsewhere")
    api_client.force_login(people.viewer)
    results = api_client.get("/api/v1/incidents/").json()["results"]
    assert [r["id"] for r in results] == [open_incident.pk]


def test_list_filters(api_client: APIClient, people: Paging, service, trigger: TriggerFn) -> None:
    a = trigger(service, "a", summary="Payments latency").incident_id
    b = trigger(service, "b", severity="warning", summary="Disk", now=T0 + timedelta(hours=1))
    api_client.force_login(people.on_call)

    def ids(query: str) -> list[int]:
        return [r["id"] for r in api_client.get(f"/api/v1/incidents/?{query}").json()["results"]]

    assert ids("urgency=low") == [b.incident_id]
    assert ids("search=payments") == [a]
    number = Incident.objects.get(pk=a).number
    assert ids(f"search=%23{number}") == [a]
    assert ids("status=acknowledged") == []
    assert ids("assignee=me") == [b.incident_id, a]
    assert ids(f"since={(T0 + timedelta(minutes=30)).isoformat().replace('+', '%2B')}") == [
        b.incident_id
    ]


def test_list_is_cursor_paginated_newest_first(
    api_client: APIClient, people: Paging, service, trigger: TriggerFn
) -> None:
    for i in range(3):
        trigger(service, f"k{i}", now=T0 + timedelta(minutes=i))
    api_client.force_login(people.on_call)

    first = api_client.get("/api/v1/incidents/?page_size=2").json()
    second = api_client.get(first["next"]).json()
    titles = [r["dedup_key"] for r in first["results"] + second["results"]]
    assert titles == ["k2", "k1", "k0"]
    assert second["next"] is None


def test_detail_includes_allowed_actions_and_a_named_snapshot(
    api_client: APIClient, open_incident: Incident, people: Paging
) -> None:
    api_client.force_login(people.on_call)
    body = api_client.get(url(open_incident)).json()

    assert body["allowed_actions"] == ["acknowledge", "resolve", "reassign", "escalate", "add_note"]
    targets = body["escalation_snapshot"]["rules"][1]["targets"]
    assert targets[0]["name"] == people.admin.name


def test_viewers_see_no_actions_and_cannot_act(
    api_client: APIClient, open_incident: Incident, people: Paging
) -> None:
    api_client.force_login(people.viewer)
    assert api_client.get(url(open_incident)).json()["allowed_actions"] == []
    response = api_client.post(url(open_incident, "acknowledge"))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_outsiders_get_404_not_403(api_client: APIClient, open_incident: Incident) -> None:
    api_client.force_login(MembershipFactory().user)
    response = api_client.get(url(open_incident))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_acknowledge_then_an_invalid_transition_is_409(
    api_client: APIClient, open_incident: Incident, people: Paging
) -> None:
    api_client.force_login(people.on_call)
    acked = api_client.post(url(open_incident, "acknowledge"))
    again = api_client.post(url(open_incident, "acknowledge"))

    assert acked.status_code == 200
    assert acked.json()["status"] == "acknowledged"
    assert acked.json()["next_escalation_at"] is None
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "invalid_transition"
    assert again.json()["error"]["details"]["allowed"] == [
        "unacknowledge",
        "resolve",
        "reassign",
        "escalate",
        "add_note",
    ]


def test_every_action_endpoint(
    api_client: APIClient, open_incident: Incident, people: Paging
) -> None:
    api_client.force_login(people.on_call)
    assert api_client.post(url(open_incident, "escalate")).json()["escalation_level"] == 1
    assert api_client.post(url(open_incident, "acknowledge")).status_code == 200
    assert api_client.post(url(open_incident, "unacknowledge")).json()["status"] == "triggered"
    reassigned = api_client.post(
        url(open_incident, "reassign"), {"assignee": people.off_call.pk}, format="json"
    )
    assert reassigned.json()["assignee"]["id"] == people.off_call.pk
    note = api_client.post(url(open_incident, "notes"), {"text": "Rolling back"}, format="json")
    assert note.status_code == 201
    assert note.json()["type"] == "note_added"
    assert api_client.post(url(open_incident, "resolve")).json()["status"] == "resolved"


def test_reassign_to_a_viewer_is_rejected(
    api_client: APIClient, open_incident: Incident, people: Paging
) -> None:
    api_client.force_login(people.on_call)
    response = api_client.post(
        url(open_incident, "reassign"), {"assignee": people.viewer.pk}, format="json"
    )
    assert response.status_code == 422


def test_overlong_note_is_limit_exceeded(
    api_client: APIClient, open_incident: Incident, people: Paging
) -> None:
    api_client.force_login(people.on_call)
    response = api_client.post(url(open_incident, "notes"), {"text": "x" * 5001}, format="json")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "limit_exceeded"


def test_timeline_and_alerts(
    api_client: APIClient, open_incident: Incident, people: Paging, trigger: TriggerFn
) -> None:
    trigger(open_incident.service, "disk-full")  # duplicate → attached
    api_client.force_login(people.on_call)

    events = api_client.get(url(open_incident, "timeline")).json()["results"]
    alerts = api_client.get(url(open_incident, "alerts")).json()["results"]
    assert [e["type"] for e in events] == ["alert_attached", "triggered"]  # newest first
    assert len(alerts) == 2
