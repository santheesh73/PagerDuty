from unittest import mock

import pytest
from django.test import Client
from redis.exceptions import ConnectionError as RedisConnectionError


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


@pytest.mark.django_db
def test_redis_down_is_degraded_not_unready(client: Client) -> None:
    """The API still accepts and commits alerts without Redis (the sweepers catch up), so a
    load balancer must keep sending it traffic."""
    with mock.patch("apps.core.health.Redis.from_url") as from_url:
        from_url.return_value.ping.side_effect = RedisConnectionError("down")
        response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "checks": {"database": "ok", "redis": "error: ConnectionError"},
    }


@pytest.mark.django_db
def test_database_down_is_unready(client: Client) -> None:
    with mock.patch("apps.core.health.connection.cursor", side_effect=RuntimeError("db gone")):
        response = client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["database"] == "error: RuntimeError"


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
