import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Service
from apps.escalations.models import EscalationPolicy
from conftest import Paging
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db
URL = "/api/v1/escalation-policies/"


def rules(people: Paging, levels: int = 2) -> list[dict]:
    return [
        {"delay_minutes": 5, "targets": [{"type": "schedule", "id": people.schedule.pk}]},
        *[{"delay_minutes": 10, "targets": [{"type": "user", "id": people.admin.pk}]}]
        * (levels - 1),
    ]


def test_create_policy_with_nested_levels(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    api_client.force_login(people.admin)
    response = api_client.post(
        URL,
        {"team": service.team_id, "name": "Payments", "num_loops": 1, "rules": rules(people)},
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert [r["level"] for r in body["rules"]] == [0, 1]
    assert body["rules"][0]["targets"][0]["name"] == people.schedule.name


def test_update_replaces_levels_atomically(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    api_client.force_login(people.admin)
    pk = service.escalation_policy_id
    response = api_client.patch(f"{URL}{pk}/", {"rules": rules(people, levels=3)}, format="json")
    assert response.status_code == 200
    assert EscalationPolicy.objects.get(pk=pk).rules.count() == 3


def test_too_many_levels_is_limit_exceeded(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    api_client.force_login(people.admin)
    response = api_client.patch(
        f"{URL}{service.escalation_policy_id}/", {"rules": rules(people, levels=11)}, format="json"
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "limit_exceeded"


def test_targets_must_belong_to_the_team(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    api_client.force_login(people.admin)
    response = api_client.patch(
        f"{URL}{service.escalation_policy_id}/",
        {"rules": [{"delay_minutes": 5, "targets": [{"type": "user", "id": UserFactory().pk}]}]},
        format="json",
    )
    assert response.status_code == 422


def test_levels_need_a_target_and_a_positive_delay(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    api_client.force_login(people.admin)
    for bad in (
        [{"delay_minutes": 5, "targets": []}],
        [{"delay_minutes": 0, "targets": [{"type": "user", "id": people.admin.pk}]}],
    ):
        response = api_client.patch(
            f"{URL}{service.escalation_policy_id}/", {"rules": bad}, format="json"
        )
        assert response.status_code == 422


def test_responders_cannot_edit_policies(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    api_client.force_login(people.on_call)
    response = api_client.patch(
        f"{URL}{service.escalation_policy_id}/", {"name": "x"}, format="json"
    )
    assert response.status_code == 403


def test_oncalls_shows_who_each_level_would_page(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    api_client.force_login(people.viewer)
    body = api_client.get("/api/v1/oncalls/").json()
    levels = body[0]["levels"]
    assert levels[0]["oncall"][0]["schedule"]["id"] == people.schedule.pk
    assert levels[0]["oncall"][0]["user"] is not None
    assert levels[1]["oncall"][0]["user"]["id"] == people.admin.pk
