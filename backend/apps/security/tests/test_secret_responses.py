"""A secret shown once is kept nowhere: not by a browser or proxy cache (`Cache-Control: no-store`),
and not by the Idempotency-Key replay store, which lives in Redis. A retry of such a request gets a
409 instead of a second copy of the secret, and the action still runs only once.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass

import pytest
from django.core.cache import caches
from django.test import Client
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.catalog.models import Service
from apps.security import mfa, totp
from apps.security.models import MfaDevice
from conftest import Paging

from .conftest import enrol, next_code

pytestmark = pytest.mark.django_db

SECRET_FIELDS = {"integration_key", "secret", "otpauth_uri", "backup_codes", "webhook_secret"}


@dataclass
class Write:
    method: str
    path: str  # the OpenAPI path template
    user: Callable[[Paging], User]
    body: Callable[[Service], dict]
    secret: Callable[[dict], str]
    prepare: Callable[[User, Service], None] = lambda user, service: None
    url: Callable[[Service], str] | None = None


def _start_mfa(user: User, _service: Service) -> None:
    mfa.begin_setup(user)


def _enrolled(user: User, _service: Service) -> None:
    client = APIClient()
    client.force_login(user)
    enrol(client)


def _with_webhook(user: User, _service: Service) -> None:
    client = APIClient()
    client.force_login(user)
    client.patch("/api/v1/me/contact/", {"webhook_url": "https://hooks.invalid/x"}, format="json")


def _confirm_code(user: User) -> dict:
    secret = MfaDevice.objects.get(user=user).secret
    return {"code": totp.code_at(secret, time.time())}


WRITES = {
    "create a service": Write(
        "POST",
        "/api/v1/services/",
        lambda p: p.admin,
        lambda s: {"name": "New", "team": s.team_id, "escalation_policy": s.escalation_policy_id},
        lambda body: body["integration_key"],
    ),
    "rotate an integration key": Write(
        "POST",
        "/api/v1/services/{id}/rotate-key/",
        lambda p: p.admin,
        lambda s: {},
        lambda body: body["integration_key"],
        url=lambda s: f"/api/v1/services/{s.pk}/rotate-key/",
    ),
    "start MFA setup": Write(
        "POST", "/api/v1/me/mfa/setup/", lambda p: p.on_call, lambda s: {}, lambda b: b["secret"]
    ),
    "confirm MFA": Write(
        "POST",
        "/api/v1/me/mfa/confirm/",
        lambda p: p.on_call,
        lambda s: {},  # filled in per test: the current TOTP code
        lambda body: body["backup_codes"][0],
        prepare=_start_mfa,
    ),
    "regenerate backup codes": Write(
        "POST",
        "/api/v1/me/mfa/backup-codes/",
        lambda p: p.on_call,
        lambda s: {},  # filled in per test: the next TOTP code
        lambda body: body["backup_codes"][0],
        prepare=_enrolled,
    ),
    "set a webhook URL": Write(
        "PATCH",
        "/api/v1/me/contact/",
        lambda p: p.on_call,
        lambda s: {"webhook_url": "https://hooks.invalid/x"},
        lambda body: body["webhook_secret"],
    ),
    "rotate the webhook secret": Write(
        "POST",
        "/api/v1/me/contact/webhook/rotate-secret/",
        lambda p: p.on_call,
        lambda s: {},
        lambda body: body["webhook_secret"],
        prepare=_with_webhook,
    ),
}


def _send(write: Write, client: Client, service: Service, body: dict, **headers: str):
    url = write.url(service) if write.url else write.path
    return client.generic(
        write.method,
        url,
        data=json.dumps(body),
        content_type="application/json",
        headers=headers,
    )


def _body(name: str, write: Write, user: User, service: Service) -> dict:
    if name == "confirm MFA":
        return _confirm_code(user)
    if name == "regenerate backup codes":
        return {"code": next_code(MfaDevice.objects.get(user=user).secret)}
    return write.body(service)


@pytest.mark.parametrize("name", list(WRITES))
def test_a_secret_shown_once_is_not_cached_or_replayed(
    name: str, service: Service, people: Paging
) -> None:
    write = WRITES[name]
    user = write.user(people)
    write.prepare(user, service)
    client = Client()
    client.force_login(user)
    body = _body(name, write, user, service)
    services_before = Service.objects.count()

    first = _send(write, client, service, body, **{"Idempotency-Key": "retry-1"})
    assert first.status_code in (200, 201), first.content
    secret = write.secret(first.json())
    assert secret
    assert "no-store" in first.get("Cache-Control", "")

    stored = b"".join(caches["default"]._cache.values())  # type: ignore[attr-defined]
    assert secret.encode() not in stored, "the replay store must never hold the secret"

    retry = _send(write, client, service, body, **{"Idempotency-Key": "retry-1"})
    assert retry.status_code == 409
    assert retry.json()["error"]["code"] == "idempotency_response_withheld"
    assert secret not in retry.content.decode()
    if name == "create a service":
        assert Service.objects.count() == services_before + 1, "the retry must not act again"


def test_ordinary_reads_of_a_service_carry_no_key_and_may_be_cached(
    service: Service, people: Paging
) -> None:
    client = Client()
    client.force_login(people.admin)
    response = client.get(f"/api/v1/services/{service.pk}/")
    assert response.json()["integration_key"] is None
    assert "no-store" not in response.get("Cache-Control", "")


def _resolve(schema: dict, node: dict) -> dict:
    while "$ref" in node:
        node = schema["components"]["schemas"][node["$ref"].rsplit("/", 1)[-1]]
    return node


def test_every_endpoint_that_can_return_a_secret_is_covered_above() -> None:
    """A new endpoint returning a secret field fails here until it is added to WRITES (and so is
    proven to be no-store and never replayed)."""
    schema = SchemaGenerator().get_schema(request=None, public=True)
    found = set()
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            for code, response in operation.get("responses", {}).items():
                if not code.startswith("2"):
                    continue
                for media in response.get("content", {}).values():
                    node = _resolve(schema, media["schema"])
                    node = _resolve(schema, node.get("items", node))
                    if SECRET_FIELDS & set(node.get("properties", {})):
                        found.add((method.upper(), path))
    covered = {(w.method, w.path) for w in WRITES.values()}
    # Every service response shares one serializer; the key is only ever filled on create and
    # rotate (covered above), and ServiceViewSet marks any response that carries it no-store.
    service_reads = {
        ("GET", "/api/v1/services/{id}/"),
        ("PUT", "/api/v1/services/{id}/"),
        ("PATCH", "/api/v1/services/{id}/"),
        ("POST", "/api/v1/services/{id}/mode/"),
    }
    assert covered <= found, "the schema walk must see every endpoint known to return a secret"
    assert found - covered - service_reads == set()
