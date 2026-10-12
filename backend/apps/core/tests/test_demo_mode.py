"""Demo mode: one container, no Redis, no Celery (docs/DEPLOY.md).

Work runs in-process right after commit, and POST /internal/tick/ does Beat's job: escalate, send
due and retried pages, end expired mode windows, stamp the heartbeat.
"""

import hmac
from datetime import timedelta
from pathlib import Path
from unittest import mock

import pytest
import time_machine
from django.core import mail
from django.core.cache import cache
from django.test import Client

from apps.catalog.models import Service
from apps.core import dispatch, tick
from apps.core.selfcheck import Check
from apps.escalations.tasks import escalate_incident
from apps.incidents.models import Incident
from apps.notifications.channels import CHANNELS, ChannelError
from apps.notifications.models import Notification
from apps.notifications.tasks import deliver_notification
from conftest import T0, Paging, TriggerFn
from tests.factories import NotificationFactory, UserFactory

pytestmark = pytest.mark.django_db

SECRET = "a-tick-secret-for-tests-only"
PENDING, SENT = Notification.Status.PENDING, Notification.Status.SENT


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    cache.clear()


@pytest.fixture
def demo(settings):  # type: ignore[no-untyped-def]
    settings.DEMO_MODE = True
    settings.DEMO_ACCOUNT_GUARD = True
    settings.TASKS_INLINE = True
    settings.TICK_SECRET = SECRET
    return settings


def post_tick(secret: str | None = SECRET, ip: str = "203.0.113.7"):  # type: ignore[no-untyped-def]
    headers = {"X-Tick-Secret": secret} if secret is not None else {}
    return Client(REMOTE_ADDR=ip).post("/internal/tick/", headers=headers)


# --- the endpoint is closed by default, and guarded when open ------------------------------------


def test_the_tick_is_off_unless_demo_mode_and_a_secret_are_both_set(settings) -> None:
    settings.TICK_SECRET = SECRET  # DEMO_MODE is off
    assert post_tick().status_code == 404
    settings.DEMO_MODE, settings.TICK_SECRET = True, ""
    response = post_tick("")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_a_missing_or_wrong_secret_is_refused_and_runs_nothing(demo) -> None:
    with mock.patch("apps.core.tick.run") as run:
        assert post_tick(None).status_code == 403
        assert post_tick("not-the-secret").status_code == 403
        assert post_tick(SECRET[:-1]).status_code == 403
    run.assert_not_called()


def test_the_secret_is_compared_in_constant_time(demo) -> None:
    with mock.patch("apps.core.tick.hmac.compare_digest", wraps=hmac.compare_digest) as compare:
        post_tick("wrong")
    compare.assert_called_once_with(b"wrong", SECRET.encode())


def test_ticks_are_rate_limited_per_address_before_the_secret_is_checked(demo) -> None:
    for _ in range(tick.RATE_LIMIT_PER_MINUTE):
        assert post_tick("guess").status_code == 403
    assert post_tick(SECRET).status_code == 429, "guessing cannot continue, even with the secret"
    assert post_tick(SECRET, ip="198.51.100.9").status_code == 200, "other callers are unaffected"


def test_only_post_ticks(demo) -> None:
    assert Client().get("/internal/tick/", headers={"X-Tick-Secret": SECRET}).status_code == 405


# --- a tick does Beat's job -------------------------------------------------------------------


def test_a_tick_escalates_an_unanswered_incident_and_sends_every_page_once(
    demo, open_incident: Incident, people: Paging
) -> None:
    # Opened at T0 inside the test transaction, so no on-commit send ran: level 1 is pending.
    assert set(open_incident.notifications.values_list("status", flat=True)) == {PENDING}
    with time_machine.travel(T0 + timedelta(minutes=6), tick=False):
        first = post_tick().json()
        second = post_tick().json()
    open_incident.refresh_from_db()
    assert first["escalated"] == 1
    assert open_incident.escalation_level == 1
    statuses = set(open_incident.notifications.values_list("status", flat=True))
    assert statuses == {SENT}, "level 1 and the new level 2 pages all went out in one tick"
    assert first["notifications_sent"] == open_incident.notifications.count()
    assert (second["escalated"], second["notifications_sent"]) == (0, 0), "nobody paged twice"
    assert people.admin.email in {m.to[0] for m in mail.outbox}


def test_a_page_whose_send_failed_is_retried_by_the_next_tick(
    demo, open_incident: Incident
) -> None:
    email = Notification.objects.filter(incident=open_incident, channel="email").first()
    assert email is not None
    with mock.patch.object(CHANNELS["email"], "send", side_effect=ChannelError("smtp down")):
        tick.run(now=T0 + timedelta(seconds=30))
    email.refresh_from_db()
    assert (email.status, email.attempts) == (PENDING, 1)
    tick.run(now=T0 + timedelta(seconds=90))
    email.refresh_from_db()
    assert (email.status, email.attempts) == (SENT, 2)


def test_a_delayed_step_is_sent_only_once_its_time_has_come(demo, open_incident: Incident) -> None:
    later = NotificationFactory(
        incident=open_incident, not_before=T0 + timedelta(minutes=3), channel="in_app"
    )
    tick.run(now=T0 + timedelta(minutes=1))
    later.refresh_from_db()
    assert later.status == PENDING
    tick.run(now=T0 + timedelta(minutes=3))
    later.refresh_from_db()
    assert later.status == SENT


def test_a_tick_ends_expired_maintenance_windows(demo, service: Service) -> None:
    Service.objects.filter(pk=service.pk).update(
        mode=Service.Mode.MAINTENANCE, mode_until=T0 - timedelta(minutes=1)
    )
    assert tick.run(now=T0)["modes_expired"] == 1
    service.refresh_from_db()
    assert service.mode == Service.Mode.ACTIVE


def test_the_heartbeat_is_stamped_and_the_dead_mans_switch_pinged_only_when_healthy(demo) -> None:
    with mock.patch("apps.core.tick.heartbeat.ping_external", return_value=True) as ping:
        result = tick.run(now=T0)
        assert result["healthy"] is True
        assert result["heartbeat_pinged"] is True
        ping.assert_called_once()
        assert cache.get("pulse:beat:last_run") == T0.timestamp()

        broken = [Check("notification delivery", False, "3 stuck pending")]
        with mock.patch("apps.core.tick.selfcheck.run", return_value=broken):
            result = tick.run(now=T0)
        assert (result["healthy"], result["heartbeat_pinged"]) == (False, False)
        ping.assert_called_once()


def test_housekeeping_runs_at_most_once_a_day(demo) -> None:
    with mock.patch("apps.core.tick.retention.purge", return_value={}) as purge:
        tick.run(now=T0)
        tick.run(now=T0 + timedelta(minutes=1))
    purge.assert_called_once()


def test_a_public_demo_is_reseeded_on_schedule_and_not_otherwise(demo) -> None:
    demo.DEMO_RESET_HOURS = 24
    with mock.patch("apps.core.tick.call_command") as reseed:
        assert tick.run(now=T0)["demo_reset"] is True
        assert "demo_reset" not in tick.run(now=T0 + timedelta(hours=1))
    reseed.assert_called_once()
    assert reseed.call_args.args == ("seed_demo", "--reset")

    demo.DEMO_RESET_HOURS = 0
    cache.clear()
    with mock.patch("apps.core.tick.call_command") as reseed:
        tick.run(now=T0)
    reseed.assert_not_called()


def test_with_self_ticking_any_request_drives_timers_at_most_once_per_interval(
    demo, open_incident: Incident
) -> None:
    demo.DEMO_SELF_TICK_SECONDS = 30
    with (
        mock.patch("apps.core.tick.run", wraps=tick.run) as run,
        time_machine.travel(T0 + timedelta(minutes=6), tick=False),
    ):
        for _ in range(3):
            assert Client().get("/healthz").status_code == 200
    run.assert_called_once()
    open_incident.refresh_from_db()
    assert open_incident.escalation_level == 1, "the timer fired without any scheduler"


def test_self_ticking_is_off_by_default_and_outside_demo_mode(settings, demo) -> None:
    with mock.patch("apps.core.tick.run") as run:
        Client().get("/healthz")  # DEMO_SELF_TICK_SECONDS is 0
        settings.DEMO_SELF_TICK_SECONDS, settings.DEMO_MODE = 30, False
        Client().get("/healthz")
    run.assert_not_called()


def test_a_failing_self_tick_never_breaks_the_request(demo) -> None:
    demo.DEMO_SELF_TICK_SECONDS = 30
    with mock.patch("apps.core.tick.run", side_effect=RuntimeError("db hiccup")):
        assert Client().get("/healthz").status_code == 200


# --- shared demo logins can't lock other visitors out -------------------------------------------


LOCKED = [
    ("post", "/api/v1/me/password/"),
    ("post", "/api/v1/me/mfa/setup/"),
    ("post", "/api/v1/me/mfa/confirm/"),
    ("post", "/api/v1/me/mfa/disable/"),
    ("post", "/api/v1/me/mfa/backup-codes/"),
]


@pytest.mark.parametrize(("method", "path"), LOCKED)
def test_demo_accounts_cannot_change_their_credentials(demo, method: str, path: str) -> None:
    client = Client()
    client.force_login(UserFactory(email="admin@demo.local"))
    response = getattr(client, method)(path, data={}, content_type="application/json")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "demo_account_locked"


def test_other_accounts_and_other_modes_are_unaffected(settings) -> None:
    client = Client()
    client.force_login(UserFactory(email="admin@demo.local"))
    assert client.post("/api/v1/me/mfa/setup/").status_code == 200, "DEMO_MODE off: allowed"

    settings.DEMO_MODE = True
    settings.DEMO_ACCOUNT_GUARD = True
    client = Client()
    client.force_login(UserFactory(email="someone@example.com"))
    assert client.post("/api/v1/me/mfa/setup/").status_code == 200, "a real account: allowed"


# --- inline dispatch: no broker anywhere ------------------------------------------------------


def test_an_alert_pages_immediately_at_commit_without_a_broker(
    demo, service: Service, trigger: TriggerFn, django_capture_on_commit_callbacks
) -> None:
    with (
        mock.patch.object(deliver_notification, "apply_async", side_effect=AssertionError),
        mock.patch.object(escalate_incident, "apply_async", side_effect=AssertionError),
        time_machine.travel(T0, tick=False),
        django_capture_on_commit_callbacks(execute=True),
    ):
        result = trigger(service, now=T0)
    incident = Incident.objects.get(pk=result.incident_id)
    assert set(incident.notifications.values_list("status", flat=True)) == {SENT}
    assert incident.escalation_level == 0, "the level-2 timer is left for the tick"


def test_inline_work_due_later_waits_for_the_tick_and_a_failure_never_escapes(
    demo, django_capture_on_commit_callbacks
) -> None:
    task = mock.MagicMock(name="task")
    with django_capture_on_commit_callbacks(execute=True):
        dispatch.on_commit(task, 1, eta=T0 + timedelta(days=3650))
    task.assert_not_called()

    task.side_effect = ChannelError("smtp down")
    with django_capture_on_commit_callbacks(execute=True):
        dispatch.on_commit(task, 2)  # must not raise into the request that committed
    task.assert_called_once_with(2)


def test_without_demo_mode_work_still_goes_to_the_broker(
    settings, django_capture_on_commit_callbacks
) -> None:
    assert settings.TASKS_INLINE is False
    task = mock.MagicMock(name="task")
    with django_capture_on_commit_callbacks(execute=True):
        dispatch.on_commit(task, 3)
    task.apply_async.assert_called_once_with(args=(3,), kwargs={})
    task.assert_not_called()


def test_readiness_does_not_depend_on_redis_in_demo_mode(demo) -> None:
    with mock.patch("apps.core.health.Redis.from_url", side_effect=AssertionError):
        response = Client().get("/readyz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "redis": "not used (demo mode)"},
    }


# --- Django serves the SPA in the one-container image -------------------------------------------


@pytest.fixture
def spa(settings, tmp_path: Path):  # type: ignore[no-untyped-def]
    (tmp_path / "index.html").write_text('<!doctype html><div id="root"></div>')
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-Ab12Cd34.js").write_text("console.log(1)")
    settings.SPA_DIR = str(tmp_path)
    settings.WHITENOISE_ROOT = str(tmp_path)
    settings.WHITENOISE_IMMUTABLE_FILE_TEST = r"^/assets/.+-[\w-]{8,}\.\w+$"
    from apps.core import spa as spa_module

    spa_module._index.cache_clear()
    return tmp_path


def test_every_client_side_route_gets_the_spa_with_its_own_policy(spa) -> None:
    for path in ("/", "/incidents", "/incidents/42", "/settings/security"):
        response = Client().get(path)
        assert response.status_code == 200, path
        assert b'id="root"' in response.content
        csp = response["Content-Security-Policy"]
        assert "script-src 'self';" in csp, "the SPA's scripts are files: no nonce"
        assert "style-src 'self' 'unsafe-inline'" in csp, "React and Recharts set style attributes"
        assert "frame-ancestors 'none'" in csp
        assert "no-cache" in response["Cache-Control"] or "max-age=0" in response["Cache-Control"]
        assert response["X-Frame-Options"] == "DENY"


def test_spa_assets_are_served_and_cached_for_good(spa) -> None:
    response = Client().get("/assets/index-Ab12Cd34.js")
    assert response.status_code == 200
    assert "immutable" in response["Cache-Control"]


def test_django_paths_never_fall_through_to_the_spa(spa) -> None:
    client = Client()
    response = client.get("/api/v1/no-such-endpoint/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert client.get("/admin").status_code == 301, "APPEND_SLASH still redirects /admin"
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.post("/incidents").status_code == 405


def test_without_an_spa_dir_unknown_paths_are_plain_404s(settings) -> None:
    assert settings.SPA_DIR == ""
    response = Client().get("/incidents")
    assert response.status_code == 404
    assert "text/html" in response["Content-Type"]


# --- visitors share a login: they must not see or end each other's sessions -------------------


def test_demo_visitors_do_not_see_each_others_address_or_browser(demo) -> None:
    from apps.security.models import SessionRecord

    user = UserFactory(email="admin@demo.local")
    SessionRecord.objects.create(
        session_key="other", user=user, ip="198.51.100.77", user_agent="VisitorOneBrowser/1.0"
    )
    client = Client()
    client.force_login(user)
    rows = client.get("/api/v1/me/sessions/").json()
    assert rows, "the list itself still works"
    assert all(r["ip"] is None and r["user_agent"] == "" for r in rows)


def test_demo_visitors_cannot_sign_each_other_out(demo) -> None:
    from apps.security.models import SessionRecord

    user = UserFactory(email="admin@demo.local")
    other = SessionRecord.objects.create(session_key="other", user=user, ip="198.51.100.77")
    client = Client()
    client.force_login(user)
    assert client.post("/api/v1/me/sessions/revoke-others/").status_code == 403
    assert client.delete(f"/api/v1/me/sessions/{other.pk}/").status_code == 403
    assert SessionRecord.objects.filter(pk=other.pk).exists()


def test_sessions_show_addresses_outside_the_demo(settings) -> None:
    from apps.security.models import SessionRecord

    assert settings.DEMO_ACCOUNT_GUARD is False
    user = UserFactory(email="admin@demo.local")
    SessionRecord.objects.create(session_key="s", user=user, ip="198.51.100.77")
    client = Client()
    client.force_login(user)
    assert any(r["ip"] == "198.51.100.77" for r in client.get("/api/v1/me/sessions/").json())


def test_the_guard_can_be_enabled_without_demo_mode(settings) -> None:
    # deploy/render-full.yaml: a full stack that seeds the shared demo logins.
    settings.DEMO_ACCOUNT_GUARD = True
    assert settings.DEMO_MODE is False
    client = Client()
    client.force_login(UserFactory(email="admin@demo.local"))
    assert client.post("/api/v1/me/mfa/setup/").status_code == 403
