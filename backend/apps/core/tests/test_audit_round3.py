"""Regression tests for the remaining findings of the final audit (docs/AUDIT.md)."""

import pytest
from django.core.cache import cache
from django.test import Client
from rest_framework.test import APIClient

from apps.security.models import AuditEvent
from tests.factories import ServiceFactory, UserFactory


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    cache.clear()


def _event(service, dedup_key: str) -> dict:
    return {
        "routing_key": service.integration_key,
        "event_action": "trigger",
        "dedup_key": dedup_key,
        "payload": {"summary": "x", "severity": "critical", "source": "t"},
    }


# --- a monitor cannot name the reserved maintenance key (L-5) ---------------------------------


@pytest.mark.django_db
def test_a_monitor_cannot_use_the_reserved_maintenance_dedup_key() -> None:
    response = APIClient().post(
        "/api/v1/events/", _event(ServiceFactory(), "__maintenance__"), format="json"
    )
    assert response.status_code == 422
    assert "dedup_key" in response.json()["error"]["details"] or "dedup_key" in str(response.json())


# --- a CSRF failure is the error envelope, not an HTML page (L-7) -----------------------------


@pytest.mark.django_db
def test_a_csrf_failure_on_sign_in_is_the_json_envelope() -> None:
    client = Client(enforce_csrf_checks=True)
    response = client.post(
        "/api/v1/auth/login/",
        {"email": "a@example.test", "password": "x"},
        content_type="application/json",
    )
    assert response.status_code == 403
    assert response["Content-Type"].startswith("application/json")
    assert response.json()["error"]["code"] == "csrf_failed"


# --- password reset does the same work for a known and an unknown address (L-2) --------------


@pytest.mark.django_db
def test_a_reset_request_for_an_unknown_address_leaves_the_same_audit_trail() -> None:
    known = UserFactory(email="known@example.test")
    client = APIClient()
    before = AuditEvent.objects.filter(action="auth.password_reset_requested").count()
    client.post("/api/v1/auth/password-reset/", {"email": known.email}, format="json")
    mid = AuditEvent.objects.filter(action="auth.password_reset_requested").count()
    client.post("/api/v1/auth/password-reset/", {"email": "nobody@example.test"}, format="json")
    after = AuditEvent.objects.filter(action="auth.password_reset_requested").count()
    assert mid == before + 1
    assert after == mid + 1, "the unknown address costs the same database write"


# --- idempotency: only a final answer is remembered; the query string is part of the request ---

from django.http import HttpResponse  # noqa: E402
from django.test import RequestFactory  # noqa: E402

from apps.core.idempotency import IdempotencyMiddleware  # noqa: E402


def _call(responses: list, path: str = "/api/v1/services/", key: str = "k-1") -> list:
    """Send the same write through the middleware once per response; return what came back."""
    user = UserFactory()
    calls = iter(responses)
    seen: list[HttpResponse] = []
    middleware = IdempotencyMiddleware(lambda request: next(calls))
    for _ in responses:
        request = RequestFactory().post(
            path, data=b"{}", content_type="application/json", HTTP_IDEMPOTENCY_KEY=key
        )
        request.user = user
        seen.append(middleware(request))
    return seen


@pytest.mark.django_db
@pytest.mark.parametrize("transient", [409, 429, 408])
def test_a_transient_refusal_is_not_replayed_to_the_retry(transient: int) -> None:
    """A 429 stored for 24 hours meant the retry, after the throttle window, got the 429 back
    and the alert was never ingested."""
    first, second = _call([HttpResponse(status=transient), HttpResponse(status=202)])
    assert first.status_code == transient
    assert second.status_code == 202
    assert "Idempotent-Replayed" not in second


@pytest.mark.django_db
def test_a_final_answer_is_replayed() -> None:
    _first, second = _call([HttpResponse(status=201, content=b"a"), HttpResponse(status=500)])
    assert second.status_code == 201
    assert second["Idempotent-Replayed"] == "true"


@pytest.mark.django_db
def test_the_query_string_is_part_of_the_request() -> None:
    user = UserFactory()
    calls = iter(
        [HttpResponse(status=200, content=b"plain"), HttpResponse(status=200, content=b"forced")]
    )
    middleware = IdempotencyMiddleware(lambda request: next(calls))
    bodies = []
    for url in ("/api/v1/services/", "/api/v1/services/?force=1"):
        request = RequestFactory().post(
            url, data=b"{}", content_type="application/json", HTTP_IDEMPOTENCY_KEY="q"
        )
        request.user = user
        bodies.append(middleware(request).content)
    assert bodies == [b"plain", b"forced"]


@pytest.mark.django_db
def test_a_response_stored_while_this_request_waited_for_the_lock_is_replayed(monkeypatch) -> None:
    """B reads "nothing stored", A finishes and releases the lock, then B's lock succeeds: B must
    look again instead of running the write a second time."""
    from apps.core import idempotency

    ran: list[int] = []
    user = UserFactory()
    middleware = IdempotencyMiddleware(lambda request: (ran.append(1), HttpResponse(status=201))[1])

    def write(key: str = "r"):
        request = RequestFactory().post(
            "/api/v1/services/",
            data=b"{}",
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=key,
        )
        request.user = user
        return middleware(request)

    write()  # A runs and stores its response

    real_get, reads = idempotency.cache.get, {"n": 0}

    def first_read_misses(key, *args):
        if key.startswith("idem:"):
            reads["n"] += 1
            if reads["n"] == 1:
                return None  # B looked before A had stored anything
        return real_get(key, *args)

    monkeypatch.setattr(idempotency.cache, "get", first_read_misses)
    response = write()  # B
    assert ran == [1], "the write ran once"
    assert response["Idempotent-Replayed"] == "true"


# --- another team's id looks exactly like one that does not exist (L-1) -----------------------


@pytest.fixture
def outsider():
    from apps.accounts.models import Membership

    a, b = ServiceFactory(), ServiceFactory()
    user = UserFactory()
    Membership.objects.create(user=user, team=b.team, role=Membership.Role.ADMIN)
    client = APIClient()
    client.force_login(user)
    return client, a


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url",
    [
        "/api/v1/services/?team={team}",
        "/api/v1/services/?escalation_policy={policy}",
        "/api/v1/escalation-policies/?team={team}",
        "/api/v1/schedules/?team={team}",
    ],
)
def test_a_filter_naming_another_teams_object_answers_like_an_unknown_id(outsider, url) -> None:
    client, other = outsider
    foreign = client.get(url.format(team=other.team_id, policy=other.escalation_policy_id))
    missing = client.get(url.format(team=99999999, policy=99999999))
    assert foreign.status_code == missing.status_code == 422
    assert foreign.json() == missing.json()


@pytest.mark.django_db
def test_a_body_naming_another_teams_object_answers_like_an_unknown_id(outsider) -> None:
    client, other = outsider

    def post(team: int, policy: int):
        return client.post(
            "/api/v1/services/",
            {"team": team, "name": "x", "escalation_policy": policy},
            format="json",
        )

    foreign = post(other.team_id, other.escalation_policy_id)
    missing = post(99999999, 99999999)
    assert foreign.status_code == missing.status_code == 422
    assert set(foreign.json()["error"]["details"]) == set(missing.json()["error"]["details"])
