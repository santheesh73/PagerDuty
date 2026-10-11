"""Metrics, the dead-man's switch, log hygiene and the Sentry scrubber."""

import logging
from datetime import UTC, datetime, timedelta

import pytest
import time_machine
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from prometheus_client.parser import text_string_to_metric_families
from pythonjsonlogger.json import JsonFormatter
from rest_framework.test import APIClient

from apps.core import heartbeat, selfcheck, sentry
from apps.core.logging import _attach_request_id, _restore_request_id, set_request_id
from apps.core.tasks import heartbeat_task
from apps.incidents.models import Status
from apps.notifications.models import Notification
from tests.factories import (
    IncidentFactory,
    NotificationFactory,
    ServiceFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

TOKEN = "metrics-token-for-tests"
NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
PAYLOAD = {"summary": "disk full", "severity": "critical", "source": "prom"}


@pytest.fixture(autouse=True)
def _enabled(settings) -> None:
    settings.METRICS_TOKEN = TOKEN
    cache.clear()


def scrape(client: Client | None = None) -> dict[tuple[str, tuple], float]:
    client = client or Client()
    response = client.get("/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200, response.content[:200]
    out: dict[tuple[str, tuple], float] = {}
    for family in text_string_to_metric_families(response.content.decode()):
        for s in family.samples:
            out[(s.name, tuple(sorted(s.labels.items())))] = s.value
    return out


def value(samples: dict, name: str, **labels: str) -> float:
    return samples.get((name, tuple(sorted(labels.items()))), 0.0)


# --- /metrics access ---------------------------------------------------------------------------


def test_metrics_are_disabled_without_a_token(settings, client: Client) -> None:
    settings.METRICS_TOKEN = ""
    assert client.get("/metrics").status_code == 404
    assert client.get("/metrics", headers={"Authorization": "Bearer "}).status_code == 404


@pytest.mark.parametrize("header", [None, "Bearer wrong", "Basic abc", f"Bearer {TOKEN}x", TOKEN])
def test_metrics_reject_anything_but_the_exact_token(client: Client, header: str | None) -> None:
    headers = {"Authorization": header} if header is not None else {}
    response = client.get("/metrics", headers=headers)
    assert response.status_code == 401
    assert b"pulse_" not in response.content


def test_metrics_expose_every_required_family() -> None:
    names = {name for name, _ in scrape()}
    required = {
        "pulse_incidents_open",
        "pulse_incidents_triggered_total",
        "pulse_incidents_resolved_total",
        "pulse_escalation_sweeper_lag_seconds",
        "pulse_escalations_overdue",
        "pulse_notifications_total",
        "pulse_notifications_stuck",
        "pulse_celery_queue_depth",
        "pulse_celery_broker_up",
    }
    assert required <= names, required - names


# --- values move with the system ---------------------------------------------------------------


def test_incident_and_notification_gauges_follow_the_database() -> None:
    before = scrape()
    open_before = value(before, "pulse_incidents_open", severity="high")
    trig_before = value(before, "pulse_incidents_triggered_total")
    res_before = value(before, "pulse_incidents_resolved_total")

    IncidentFactory(urgency="high")
    resolved = IncidentFactory(status=Status.RESOLVED)
    NotificationFactory(
        incident=resolved, status=Notification.Status.FAILED, channel=Notification.Channel.EMAIL
    )

    after = scrape()
    assert value(after, "pulse_incidents_open", severity="high") == open_before + 1
    assert value(after, "pulse_incidents_triggered_total") == trig_before + 2
    assert value(after, "pulse_incidents_resolved_total") == res_before + 1
    failed = {"channel": "email", "status": "failed"}
    assert value(after, "pulse_notifications_total", **failed) == (
        value(before, "pulse_notifications_total", **failed) + 1
    )


def test_ingest_counters_split_accepted_from_rejected() -> None:
    service = ServiceFactory()
    client = APIClient()
    before = scrape()

    ok = client.post(
        "/api/v1/events/",
        {
            "routing_key": service.integration_key,
            "event_action": "trigger",
            "payload": PAYLOAD,
        },
        format="json",
    )
    assert ok.status_code == 202
    bad = client.post(
        "/api/v1/events/",
        {"routing_key": "x" * 32, "event_action": "trigger", "payload": PAYLOAD},
        format="json",
    )
    assert bad.status_code == 403

    after = scrape()
    assert value(after, "pulse_ingest_requests_total", result="accepted") == (
        value(before, "pulse_ingest_requests_total", result="accepted") + 1
    )
    assert value(after, "pulse_ingest_requests_total", result="rejected_403") == (
        value(before, "pulse_ingest_requests_total", result="rejected_403") + 1
    )
    assert value(after, "pulse_ingest_latency_seconds_count") == (
        value(before, "pulse_ingest_latency_seconds_count") + 2
    )


def test_http_metrics_use_route_templates_not_raw_paths() -> None:
    Client().get("/healthz")
    Client().get("/api/v1/incidents/987654/")  # unauthenticated 403; path has an id in it
    names = {dict(labels).get("route") for (name, labels) in scrape() if "route" in dict(labels)}
    assert "api/v1/incidents/{pk}/" in names
    assert not any("987654" in (r or "") for r in names)


def test_delivery_histogram_buckets_by_time_to_send() -> None:
    fast = NotificationFactory(status=Notification.Status.SENT, channel="email")
    slow = NotificationFactory(status=Notification.Status.SENT, channel="email")
    Notification.objects.filter(pk=fast.pk).update(sent_at=fast.created_at + timedelta(seconds=3))
    Notification.objects.filter(pk=slow.pk).update(sent_at=slow.created_at + timedelta(seconds=100))
    samples = scrape()
    base = "pulse_notification_delivery_seconds"
    assert value(samples, f"{base}_bucket", channel="email", le="5.0") == 1
    assert value(samples, f"{base}_bucket", channel="email", le="120.0") == 2
    assert value(samples, f"{base}_count", channel="email") == 2


# --- sweeper lag under a frozen clock ----------------------------------------------------------


def test_sweeper_lag_gauge_is_exactly_the_oldest_overdue_timer() -> None:
    with time_machine.travel(NOW, tick=False):
        assert value(scrape(), "pulse_escalation_sweeper_lag_seconds") == 0.0

        IncidentFactory(status=Status.TRIGGERED, next_escalation_at=NOW - timedelta(seconds=45))
        IncidentFactory(status=Status.TRIGGERED, next_escalation_at=NOW - timedelta(seconds=120))
        IncidentFactory(status=Status.TRIGGERED, next_escalation_at=NOW + timedelta(seconds=300))
        IncidentFactory(status=Status.ACKNOWLEDGED, next_escalation_at=NOW - timedelta(hours=1))

        samples = scrape()
        assert value(samples, "pulse_escalation_sweeper_lag_seconds") == 120.0
        assert value(samples, "pulse_escalations_overdue") == 2.0


def test_stuck_notifications_are_pending_for_over_five_minutes() -> None:
    with time_machine.travel(NOW, tick=False):
        old = NotificationFactory(status=Notification.Status.PENDING)
        fresh = NotificationFactory(status=Notification.Status.PENDING)
        Notification.objects.filter(pk=old.pk).update(updated_at=NOW - timedelta(minutes=6))
        Notification.objects.filter(pk=fresh.pk).update(updated_at=NOW - timedelta(minutes=1))
        samples = scrape()
        assert value(samples, "pulse_notifications_stuck") == 1.0
        assert value(samples, "pulse_notifications_pending") == 2.0


# --- dead-man's switch -------------------------------------------------------------------------


def test_selfcheck_fails_when_beat_has_never_run_and_passes_after_a_heartbeat(capsys) -> None:
    with time_machine.travel(NOW, tick=False):
        with pytest.raises(CommandError):
            call_command("selfcheck")
        heartbeat.record()
        call_command("selfcheck")
        assert "ok   beat heartbeat" in capsys.readouterr().out


def test_selfcheck_notices_a_stalled_beat_and_a_lagging_sweeper() -> None:
    with time_machine.travel(NOW, tick=False):
        heartbeat.record(NOW.timestamp() - heartbeat.BEAT_STALE_AFTER - 1)
        failed = {c.name for c in selfcheck.run() if not c.ok}
        assert failed == {"beat heartbeat"}

        heartbeat.record()
        IncidentFactory(
            status=Status.TRIGGERED,
            next_escalation_at=NOW - timedelta(seconds=selfcheck.SWEEPER_LAG_LIMIT + 1),
        )
        failed = {c.name for c in selfcheck.run() if not c.ok}
        assert failed == {"escalation sweeper"}


def test_heartbeat_pings_only_while_the_stack_is_healthy(monkeypatch) -> None:
    pings: list[str] = []
    monkeypatch.setattr(heartbeat, "ping_external", lambda: pings.append("ping") or True)

    with time_machine.travel(NOW, tick=False):
        assert heartbeat_task() is True
        assert pings == ["ping"]
        assert heartbeat.last_run() == NOW.timestamp()

        # A stalled sweeper must go quiet so the external monitor fires.
        IncidentFactory(status=Status.TRIGGERED, next_escalation_at=NOW - timedelta(minutes=10))
        assert heartbeat_task() is False
        assert pings == ["ping"]
        assert heartbeat.last_run() == NOW.timestamp()  # Beat itself is still recorded


def test_ping_really_makes_the_request_and_reports_the_monitors_answer() -> None:
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            seen.append(self.path)
            self.send_response(200 if self.path == "/ok" else 500)
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        assert heartbeat.ping_external(f"{base}/ok") is True
        assert heartbeat.ping_external(f"{base}/down") is False  # monitor error: no raise
        assert seen == ["/ok", "/down"]
    finally:
        server.shutdown()


def test_ping_never_raises_and_refuses_non_http_urls(settings) -> None:
    assert heartbeat.ping_external("") is False
    assert heartbeat.ping_external("file:///etc/passwd") is False
    assert heartbeat.ping_external("http://127.0.0.1:9/unreachable") is False


# --- logs --------------------------------------------------------------------------------------


def _render(records: list[logging.LogRecord]) -> str:
    formatter = JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    return "\n".join(formatter.format(r) for r in records)


def test_login_and_ingest_logs_never_contain_credentials(caplog: pytest.LogCaptureFixture) -> None:
    password = "Zq9-unique-password-7731"
    user = UserFactory()
    user.set_password(password)
    user.save()
    service = ServiceFactory()
    client = APIClient()
    caplog.set_level(logging.DEBUG)

    ok = client.post(
        "/api/v1/auth/login/?token=qs-secret-123",
        {"email": user.email, "password": password},
        format="json",
    )
    assert ok.status_code == 200
    client.post(
        "/api/v1/auth/login/", {"email": user.email, "password": password + "x"}, format="json"
    )
    session = client.cookies["sessionid"].value
    client.post(
        "/api/v1/events/",
        {
            "routing_key": service.integration_key,
            "event_action": "trigger",
            "payload": PAYLOAD,
        },
        format="json",
    )
    client.post(
        "/api/v1/events/",
        {"routing_key": "wrong-key-value-9999", "event_action": "trigger", "payload": PAYLOAD},
        format="json",
    )

    rendered = _render(caplog.records)
    assert "request" in rendered  # the access log really ran, so absence below means something
    for secret in (
        password,
        service.integration_key,
        "wrong-key-value-9999",
        session,
        "qs-secret-123",
    ):
        assert secret not in rendered, f"{secret!r} leaked into the logs"


def test_request_id_is_carried_into_celery_and_restored_in_the_worker() -> None:
    token = set_request_id("trace-abcdef12")
    headers: dict = {}
    _attach_request_id(headers=headers)
    assert headers["request_id"] == "trace-abcdef12"

    class Request:
        request_id = "trace-abcdef12"

    class Task:
        request = Request()

    set_request_id(None)
    _restore_request_id(task=Task())
    from apps.core.logging import get_request_id

    assert get_request_id() == "trace-abcdef12"
    set_request_id(None)
    del token


def test_production_logging_redacts_the_request_object_django_attaches() -> None:
    """`django.request` records carry the request, whose repr includes the query string."""
    import logging.config

    from config.settings import base

    logging.config.dictConfig(base.LOGGING)
    try:
        stream_handler = logging.getLogger().handlers[0]
        record = logging.LogRecord(
            "django.request", logging.WARNING, "x", 1, "Forbidden", None, None
        )
        record.request = "<WSGIRequest: GET '/api/v1/incidents/1/?routing_key=LEAKME'>"
        for flt in stream_handler.filters:
            flt.filter(record)
        assert "LEAKME" not in stream_handler.format(record)
    finally:
        logging.config.dictConfig({"version": 1, "disable_existing_loggers": False})


def test_worker_logs_stay_json(settings) -> None:
    assert settings.CELERY_WORKER_HIJACK_ROOT_LOGGER is False


# --- Sentry ------------------------------------------------------------------------------------


def test_sentry_scrubber_removes_cookies_bodies_headers_and_secret_keys() -> None:
    event = {
        "request": {
            "url": "https://pulse.example/api/v1/events/",
            "query_string": "routing_key=abc",
            "cookies": {"sessionid": "S3SSION"},
            "data": {"routing_key": "R0UTING", "payload": {"summary": "x"}},
            "headers": {
                "Authorization": "Bearer T0KEN",
                "Cookie": "sessionid=S3SSION",
                "X-CSRFToken": "CSRF",
                "User-Agent": "curl",
            },
        },
        "user": {"id": 7, "email": "a@b.c", "ip_address": "1.2.3.4"},
        "extra": {"password": "hunter2", "nested": [{"api_key": "K", "ok": "fine"}]},
        "breadcrumbs": {"values": [{"data": {"integration_key": "IK", "n": 1}}]},
        "exception": {"values": [{"value": "boom"}]},
    }
    cleaned = sentry.before_send(event)
    blob = repr(cleaned)
    for secret in ("S3SSION", "R0UTING", "T0KEN", "CSRF", "hunter2", "'K'", "'IK'", "a@b.c"):
        assert secret not in blob, secret
    assert cleaned["request"]["headers"] == {"User-Agent": "curl"}
    assert cleaned["extra"]["nested"][0]["ok"] == "fine"  # non-secrets survive
    assert cleaned["exception"]["values"][0]["value"] == "boom"


def test_sentry_is_not_initialised_without_a_dsn(settings) -> None:
    import sentry_sdk

    assert settings.SENTRY_DSN == ""
    assert not sentry_sdk.get_client().is_active()
