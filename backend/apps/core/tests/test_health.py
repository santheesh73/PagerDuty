import pytest
from django.test import Client


def test_healthz_is_up_without_touching_backends(client: Client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_readyz_reports_each_backend(client: Client) -> None:
    response = client.get("/readyz")
    body = response.json()
    assert body["checks"]["database"] == "ok"
    assert set(body["checks"]) == {"database", "redis"}


def test_request_id_is_echoed_when_valid(client: Client) -> None:
    response = client.get("/healthz", headers={"X-Request-ID": "abc12345-trace"})
    assert response["X-Request-ID"] == "abc12345-trace"


def test_request_id_is_replaced_when_malformed(client: Client) -> None:
    response = client.get("/healthz", headers={"X-Request-ID": "<script>"})
    assert response["X-Request-ID"] != "<script>"
    assert len(response["X-Request-ID"]) == 32


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/incidents/",
        "/api/v1/services/",
        "/api/v1/escalation-policies/",
        "/api/v1/schedules/",
        "/api/v1/notifications/",
        "/api/v1/oncalls/",
        "/api/v1/teams/",
        "/api/v1/users/",
        "/api/v1/analytics/summary/",
        "/api/v1/schedules/1/overrides/",
    ],
)
def test_every_api_endpoint_requires_authentication(client: Client, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_authenticated"
