"""API contract: stable pagination, one error envelope everywhere, size limits, idempotent retries."""

from unittest import mock

import pytest
from django.core.cache import cache
from django.core.exceptions import RequestDataTooBig
from django.test import Client
from redis.exceptions import ConnectionError as RedisConnectionError
from rest_framework.test import APIClient, APIRequestFactory

from apps.catalog.models import Service
from apps.core.throttling import RoutingKeyThrottle
from apps.incidents.models import EventType, Incident
from conftest import T0, Paging
from tests.factories import IncidentFactory, ScheduleFactory, ServiceFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    cache.clear()


def staff_client() -> APIClient:
    client = APIClient()
    client.force_login(UserFactory(is_staff=True))
    return client


# --- pagination ---------------------------------------------------------------------------------


def test_cursor_pages_never_skip_or_repeat_incidents_that_share_a_timestamp() -> None:
    """Regression: ordering by triggered_at alone skipped 6-10 of 25 tied rows under concurrent
    updates (reproduced before the fix: 15-19 unique ids out of 25)."""
    service = ServiceFactory()
    for _ in range(25):
        IncidentFactory(service=service, triggered_at=T0)
    client = staff_client()
    seen, url = [], "/api/v1/incidents/?page_size=10"
    while url:
        body = client.get(url).json()
        seen += [row["id"] for row in body["results"]]
        for incident in Incident.objects.order_by("?")[:10]:  # activity between page loads
            Incident.objects.filter(pk=incident.pk).update(title=incident.title + ".")
        url = body["next"]
    assert len(seen) == 25
    assert len(set(seen)) == 25


def _list_querysets():
    """(name, queryset) for every list endpoint, built the way its view builds it."""
    from config.api_urls import router

    factory = APIRequestFactory()
    staff = UserFactory(is_staff=True)
    for prefix, viewset, _ in router.registry:
        if not hasattr(viewset, "list"):
            continue
        request = factory.get(f"/api/v1/{prefix}/")
        request.user = staff
        view = viewset()
        view.action_map = {"get": "list"}
        view.action = "list"
        view.format_kwarg = None
        view.args, view.kwargs = (), {}
        view.request = view.initialize_request(request)
        view.request.user = staff
        yield prefix, viewset, view.get_queryset()


def test_every_list_has_a_total_order_ending_in_a_unique_field() -> None:
    for prefix, viewset, queryset in _list_querysets():
        pagination = getattr(viewset, "pagination_class", None)
        ordering = getattr(pagination, "ordering", None) if pagination else None
        fields = list(ordering) if isinstance(ordering, (tuple, list)) else []
        fields = fields or list(queryset.query.order_by) or list(queryset.model._meta.ordering)
        assert fields, f"{prefix}: no ordering at all"
        # `position` is unique per user (uniq_rule_position) and that list is always one user's.
        assert fields[-1].lstrip("-") in {"id", "pk", "user_id", "position"}, (
            f"{prefix}: ordering {fields} has no unique tie-breaker, so pages are not stable"
        )


# --- errors -------------------------------------------------------------------------------------


def test_unknown_api_paths_answer_with_the_json_envelope() -> None:
    response = Client().get("/api/v1/no-such-thing/")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "No such endpoint.", "details": {}}
    }


def test_non_api_404s_stay_html() -> None:
    response = Client().get("/no-such-page")
    assert response.status_code == 404
    assert "text/html" in response["Content-Type"]


def test_an_unhandled_crash_answers_json_with_the_request_id() -> None:
    client = Client(raise_request_exception=False)
    client.force_login(UserFactory(is_staff=True))
    with mock.patch("apps.incidents.views.IncidentViewSet.list", side_effect=RuntimeError("boom")):
        response = client.get("/api/v1/incidents/", headers={"X-Request-ID": "trace-12345678"})
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "server_error"
    assert "trace-12345678" in body["error"]["message"]
    assert "boom" not in response.content.decode(), "internals never reach the client"


@pytest.mark.parametrize("sent", [None, "<script>alert(1)</script>"])
def test_the_500_names_the_logged_request_id_never_raw_header_input(sent: str | None) -> None:
    client = Client(raise_request_exception=False)
    client.force_login(UserFactory(is_staff=True))
    headers = {"X-Request-ID": sent} if sent else {}
    with mock.patch("apps.incidents.views.IncidentViewSet.list", side_effect=RuntimeError("boom")):
        response = client.get("/api/v1/incidents/", headers=headers)
    assert response.status_code == 500
    message = response.json()["error"]["message"]
    assert response["X-Request-ID"] in message, "the id support can grep the logs for"
    assert "<script>" not in message


# Every one of these once answered 500 or silently ignored the filter (returning everything or
# nothing). A bad query parameter is the caller's mistake: 422 naming the parameter.
BAD_QUERIES = [
    ("/api/v1/users/?team=abc", "team"),
    ("/api/v1/schedules/{schedule}/overrides/?since=bad", "since"),
    ("/api/v1/incidents/?status=bogus", "status"),
    ("/api/v1/incidents/?status=triggered,bogus", "status"),
    ("/api/v1/incidents/?urgency=bogus", "urgency"),
    ("/api/v1/incidents/?assignee=xyz", "assignee"),
    ("/api/v1/incidents/?service=abc", "service"),
    ("/api/v1/incidents/?since=garbage", "since"),
    ("/api/v1/analytics/summary/?team=abc", "team"),
    ("/api/v1/analytics/timeseries/?service=1x", "service"),
    ("/api/v1/services/?mode=bogus", "mode"),
    ("/api/v1/audit-events/?team=abc", "team"),
    # Well-formed but impossible instants once answered 500 (found by the final audit).
    ("/api/v1/incidents/?since=2026-02-30T00:00:00Z", "since"),
    ("/api/v1/incidents/?since=2026-01-01T00:00:00%2B25:00", "since"),
    ("/api/v1/incidents/?until=2026-01-01T25:00:00", "until"),
    ("/api/v1/analytics/summary/?since=2026-02-30T00:00:00Z", "since"),
    ("/api/v1/analytics/timeseries/?since=0001-01-01T00:00:00Z", "since"),
    (
        "/api/v1/analytics/timeseries/?since=9999-06-01T00:00:00Z&until=9999-12-31T23:00:00Z",
        "since",
    ),
]


@pytest.mark.parametrize(("url", "param"), BAD_QUERIES)
def test_a_bad_query_parameter_is_a_422_naming_it(url: str, param: str) -> None:
    client = Client(raise_request_exception=False)
    client.force_login(UserFactory(is_staff=True))
    response = client.get(url.format(schedule=ScheduleFactory().pk))
    assert response.status_code == 422, response.content
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert param in error["details"]


def test_valid_filters_still_filter(service: Service, people: Paging) -> None:
    client = APIClient()
    client.force_login(people.admin)
    low = IncidentFactory(service=service, urgency="low", assignee=people.admin)
    IncidentFactory(service=service, urgency="high", assignee=people.admin)
    response = client.get(
        "/api/v1/incidents/?status=triggered,acknowledged&urgency=low&assignee=me"
    )
    assert [row["id"] for row in response.json()["results"]] == [low.pk]
    response = client.get(f"/api/v1/users/?team={service.team_id}")
    assert response.status_code == 200
    assert response.json()


def test_malformed_json_is_a_400_envelope() -> None:
    response = APIClient().post("/api/v1/auth/login/", "{nope", content_type="application/json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "parse_error"


def test_validation_errors_are_422_with_field_details(people: Paging) -> None:
    client = APIClient()
    client.force_login(people.admin)
    response = client.post("/api/v1/services/", {"name": ""}, format="json")
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_error"
    assert "name" in body["details"]


# --- size limits --------------------------------------------------------------------------------


def test_bodies_over_the_limit_are_413_before_any_view_reads_them(settings) -> None:
    big = b'{"x":"' + b"a" * (settings.DATA_UPLOAD_MAX_MEMORY_SIZE + 10) + b'"}'
    with (
        mock.patch("apps.alerting.views.EventsView.post") as events,
        mock.patch("apps.accounts.views.LoginView.post") as login,
        mock.patch.object(RoutingKeyThrottle, "allow_request") as throttle,
    ):
        for path in ("/api/v1/events/", "/api/v1/auth/login/"):
            response = Client().post(path, data=big, content_type="application/json")
            assert response.status_code == 413, path
            assert response.json()["error"]["code"] == "payload_too_large"
    assert not events.called, "rejected before any view ran"
    assert not login.called
    assert not throttle.called


def test_a_body_too_big_to_read_is_413_even_without_content_length(people: Paging) -> None:
    client = APIClient()
    client.force_login(people.admin)
    with mock.patch("apps.catalog.views.ServiceViewSet.create", side_effect=RequestDataTooBig("x")):
        response = client.post("/api/v1/services/", {}, format="json")
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_throttles_fail_open_only_when_the_cache_is_down() -> None:
    """They used to swallow every exception, which logged an oversized body as a cache outage."""
    request = APIRequestFactory().post("/api/v1/events/", {}, format="json")
    throttle = RoutingKeyThrottle()
    with mock.patch.object(RoutingKeyThrottle, "get_cache_key", side_effect=RedisConnectionError()):
        assert throttle.allow_request(request, None) is True
    with (
        mock.patch.object(RoutingKeyThrottle, "get_cache_key", side_effect=RequestDataTooBig()),
        pytest.raises(RequestDataTooBig),
    ):
        throttle.allow_request(request, None)


# --- idempotency --------------------------------------------------------------------------------


def test_a_retried_write_with_the_same_key_acts_once_and_replays_the_response(
    open_incident: Incident, people: Paging
) -> None:
    client = APIClient()
    client.force_login(people.on_call)
    url = f"/api/v1/incidents/{open_incident.pk}/acknowledge/"
    first = client.post(url, HTTP_IDEMPOTENCY_KEY="retry-1")
    second = client.post(url, HTTP_IDEMPOTENCY_KEY="retry-1")
    assert first.status_code == second.status_code == 200
    assert second["Idempotent-Replayed"] == "true"
    assert second.json() == first.json()
    assert open_incident.events.filter(type=EventType.ACKNOWLEDGED).count() == 1


def test_reusing_a_key_with_a_different_body_is_refused(people: Paging, service) -> None:
    client = APIClient()
    client.force_login(people.admin)
    url = f"/api/v1/services/{service.pk}/"
    assert (
        client.patch(
            url, {"description": "a"}, format="json", HTTP_IDEMPOTENCY_KEY="k1"
        ).status_code
        == 200
    )
    reused = client.patch(url, {"description": "b"}, format="json", HTTP_IDEMPOTENCY_KEY="k1")
    assert reused.status_code == 422
    assert reused.json()["error"]["code"] == "idempotency_key_reused"
    service.refresh_from_db()
    assert service.description == "a"


def test_keys_are_scoped_to_the_caller(open_incident: Incident, people: Paging) -> None:
    url = f"/api/v1/incidents/{open_incident.pk}/notes/"
    one, two = APIClient(), APIClient()
    one.force_login(people.on_call)
    two.force_login(people.admin)
    a = one.post(url, {"text": "x"}, format="json", HTTP_IDEMPOTENCY_KEY="same")
    b = two.post(url, {"text": "x"}, format="json", HTTP_IDEMPOTENCY_KEY="same")
    assert a.status_code in (200, 201)
    assert "Idempotent-Replayed" not in b, "another user's key must never replay to me"


def test_the_events_api_honours_the_key_per_routing_key(service) -> None:
    from apps.alerting.models import Alert

    body = {
        "routing_key": service.integration_key,
        "event_action": "trigger",
        "payload": {"summary": "x", "severity": "critical", "source": "t"},
    }
    client = APIClient()
    first = client.post("/api/v1/events/", body, format="json", HTTP_IDEMPOTENCY_KEY="evt-1")
    second = client.post("/api/v1/events/", body, format="json", HTTP_IDEMPOTENCY_KEY="evt-1")
    assert first.status_code == second.status_code == 202
    assert second["Idempotent-Replayed"] == "true"
    assert Alert.objects.filter(service=service).count() == 1


@pytest.mark.parametrize("bad", ["", "has space", "x" * 300, "ünïcode"])
def test_malformed_keys_are_rejected(people: Paging, service, bad: str) -> None:
    client = APIClient()
    client.force_login(people.admin)
    response = client.patch(
        f"/api/v1/services/{service.pk}/",
        {"description": "a"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=bad,
    )
    assert response.status_code == 400 or (bad == "" and response.status_code in (200, 400))


def test_a_cache_outage_runs_the_request_without_replay(
    open_incident: Incident, people: Paging
) -> None:
    client = APIClient()
    client.force_login(people.on_call)
    with mock.patch("apps.core.idempotency.cache.get", side_effect=RedisConnectionError()):
        response = client.post(
            f"/api/v1/incidents/{open_incident.pk}/acknowledge/", HTTP_IDEMPOTENCY_KEY="k"
        )
    assert response.status_code == 200
