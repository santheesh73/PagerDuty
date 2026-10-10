import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Service
from conftest import Paging
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db
URL = "/api/v1/schedules/"


def layer(people: Paging, **extra: object) -> dict:
    return {
        "name": "Primary",
        "rotation_type": "daily",
        "turn_count": 1,
        "start": "2026-01-05T09:00:00Z",
        "handoff_time": "09:00:00",
        "members": [people.on_call.pk, people.off_call.pk],
        **extra,
    }


def test_create_schedule_with_layers(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    api_client.force_login(people.admin)
    response = api_client.post(
        URL,
        {
            "team": service.team_id,
            "name": "Payments",
            "timezone": "America/New_York",
            "layers": [
                layer(people),
                layer(people, name="Follow the sun", rotation_type="custom", turn_length_hours=12),
            ],
        },
        format="json",
    )
    assert response.status_code == 201
    layers = response.json()["layers"]
    assert [(lay["name"], lay["priority"]) for lay in layers] == [
        ("Primary", 2),
        ("Follow the sun", 1),
    ]
    assert layers[1]["turn_length_hours"] == 12
    assert [m["id"] for m in layers[0]["member_details"]] == [people.on_call.pk, people.off_call.pk]


def test_custom_layers_need_a_turn_length(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    api_client.force_login(people.admin)
    response = api_client.post(
        URL,
        {
            "team": service.team_id,
            "name": "x",
            "timezone": "UTC",
            "layers": [layer(people, rotation_type="custom")],
        },
        format="json",
    )
    assert response.status_code == 422


def test_layer_members_must_be_on_the_team(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    api_client.force_login(people.admin)
    response = api_client.put(
        f"{URL}{people.schedule.pk}/",
        {
            "team": service.team_id,
            "name": "x",
            "timezone": "UTC",
            "layers": [layer(people, members=[UserFactory().pk])],
        },
        format="json",
    )
    assert response.status_code == 422


def test_too_many_layers_is_limit_exceeded(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    api_client.force_login(people.admin)
    response = api_client.patch(
        f"{URL}{people.schedule.pk}/", {"layers": [layer(people)] * 6}, format="json"
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "limit_exceeded"


def test_invalid_timezone_is_rejected(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    api_client.force_login(people.admin)
    response = api_client.patch(
        f"{URL}{people.schedule.pk}/", {"timezone": "Mars/Olympus"}, format="json"
    )
    assert response.status_code == 422


def test_oncall_and_shifts_endpoints(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    api_client.force_login(people.viewer)
    now = api_client.get(f"{URL}{people.schedule.pk}/oncall/?at=2026-01-07T12:00:00Z").json()
    assert now["user"]["id"] == people.on_call.pk

    shifts = api_client.get(
        f"{URL}{people.schedule.pk}/shifts/?since=2026-01-07T09:00:00Z&until=2026-01-09T09:00:00Z"
    ).json()
    assert [s["user"]["id"] for s in shifts] == [people.on_call.pk, people.off_call.pk]

    too_wide = api_client.get(
        f"{URL}{people.schedule.pk}/shifts/?since=2026-01-01T00:00:00Z&until=2026-06-01T00:00:00Z"
    )
    assert too_wide.status_code == 422


def test_overrides_crud_and_effect_on_oncall(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    base = f"{URL}{people.schedule.pk}/overrides/"
    body = {"user": people.admin.pk, "start": "2026-01-07T10:00:00Z", "end": "2026-01-07T14:00:00Z"}

    api_client.force_login(people.on_call)
    assert api_client.post(base, body, format="json").status_code == 403

    api_client.force_login(people.admin)
    created = api_client.post(base, body, format="json")
    assert created.status_code == 201
    now = api_client.get(f"{URL}{people.schedule.pk}/oncall/?at=2026-01-07T12:00:00Z").json()
    assert (now["user"]["id"], now["source"]) == (people.admin.pk, "override")

    backwards = api_client.post(base, {**body, "end": "2026-01-07T09:00:00Z"}, format="json")
    assert backwards.status_code == 422
    assert len(api_client.get(base).json()) == 1
    assert api_client.delete(f"{base}{created.json()['id']}/").status_code == 204
