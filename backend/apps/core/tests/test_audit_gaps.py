"""Guards the final audit found unpinned: each of these mutations once survived the whole suite.

Mutations are named in scripts/mutate.py; every test here fails when its target line is broken.
"""

import hashlib
import subprocess
import sys
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest
from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from rest_framework.test import APIClient

from apps.analytics.selectors import incidents_in  # noqa: F401  (scoping lives beside it)
from apps.catalog.actions import service_for_key
from apps.incidents.models import Incident
from apps.notifications.actions import _claim
from apps.notifications.models import Notification
from tests.factories import ServiceFactory, UserFactory

BACKEND = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    cache.clear()


def _event(service, summary: str = "x") -> dict:
    return {
        "routing_key": service.integration_key,
        "event_action": "trigger",
        "payload": {"summary": summary, "severity": "critical", "source": "t"},
    }


# --- idempotency ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_retry_while_the_first_attempt_is_running_is_refused_not_run_twice() -> None:
    user = UserFactory(is_staff=True)
    client = APIClient()
    client.force_login(user)  # the middleware reads the session user, not DRF's
    scope, path, key = f"user:{user.pk}", "/api/v1/services/", "retry-1"
    name = hashlib.sha256(f"{scope}|POST|{path}?|{key}".encode()).hexdigest()
    cache.set(f"idem-lock:{name}", 1, timeout=60)  # the first attempt holds the lock

    response = client.post(path, {"name": "x"}, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_in_progress"


@pytest.mark.django_db
def test_the_same_idempotency_key_on_two_services_ingests_both() -> None:
    """Scoped per routing key. One shared scope would replay service A's 202 to service B and
    B's page would never be created."""
    a, b = ServiceFactory(), ServiceFactory()
    client = APIClient()
    first = client.post("/api/v1/events/", _event(a), format="json", HTTP_IDEMPOTENCY_KEY="same")
    second = client.post(
        "/api/v1/events/", _event(b, "y"), format="json", HTTP_IDEMPOTENCY_KEY="same"
    )
    assert first.status_code == second.status_code == 202
    assert "Idempotent-Replayed" not in second
    assert Incident.objects.filter(service=b).exists()


# --- keys ----------------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_notification_idempotency_key_is_unique_in_the_database(open_incident: Incident) -> None:
    row = Notification.objects.filter(incident=open_incident).first()
    assert row is not None
    with pytest.raises(IntegrityError), transaction.atomic():
        Notification.objects.create(
            incident=row.incident,
            user=row.user,
            channel=row.channel,
            idempotency_key=row.idempotency_key,
        )


@pytest.mark.django_db
def test_a_key_sharing_only_the_prefix_is_not_a_key() -> None:
    service = ServiceFactory()
    near_miss = service.integration_key[:8] + "0" * 56
    assert near_miss != service.integration_key
    assert service_for_key(near_miss) is None
    assert service_for_key(service.integration_key) == service


# --- the claim holds the row ---------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_claiming_a_row_waits_for_whoever_holds_its_lock(open_incident: Incident) -> None:
    """The row lock is what serialises two workers; without it both would claim the row."""
    row = Notification.objects.get(incident=open_incident, channel="email")
    held, release = threading.Event(), threading.Event()

    def holder() -> None:
        try:
            with transaction.atomic():
                Notification.objects.select_for_update().get(pk=row.pk)
                held.set()
                release.wait(5)
        finally:
            connection.close()

    thread = threading.Thread(target=holder)
    thread.start()
    held.wait(5)
    started = time.monotonic()
    waited = {}

    def release_soon() -> None:
        time.sleep(0.4)
        release.set()

    threading.Thread(target=release_soon).start()
    from django.utils import timezone

    _claim(row.pk, timezone.now())
    waited["s"] = time.monotonic() - started
    thread.join()
    assert waited["s"] >= 0.3, "the claim must block while another transaction holds the row"


# --- production flags ----------------------------------------------------------------------

_PROD_ENV = {
    "SECRET_KEY": "k3Y-" + "q7Zp1Vw9Xr5Tn2Bm8Lc4Hd6Gf0Js" * 2,
    "ALLOWED_HOSTS": "pulse.example.test",
    "DATABASE_URL": "postgres://pulse:pulse@localhost:5432/pulse",
    "NUM_PROXIES": "1",
}


def _prod(expr: str, **env: str) -> str:
    import os

    clean = {k: v for k, v in os.environ.items() if k not in _PROD_ENV}
    result = subprocess.run(  # noqa: S603 (this interpreter, fixed arguments)
        [sys.executable, "-c", f"import config.settings.prod as s; print({expr})"],
        cwd=BACKEND,
        env={**clean, **_PROD_ENV, **env},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_production_defaults_are_the_safe_ones() -> None:
    assert _prod("s.SECURE_HSTS_SECONDS") == str(365 * 24 * 3600)
    assert _prod("s.SESSION_COOKIE_SECURE and s.CSRF_COOKIE_SECURE") == "True"
    assert _prod("s.SESSION_COOKIE_HTTPONLY") == "True"
    assert _prod("s.SESSION_COOKIE_SAMESITE") == "Lax"
    assert _prod("s.SESSION_COOKIE_NAME") == "__Host-sessionid"
    assert _prod("s.SECURE_SSL_REDIRECT") == "True"
    assert _prod("s.SECURE_CONTENT_TYPE_NOSNIFF") == "True"


def test_check_deploy_is_clean_under_production_settings() -> None:
    import os

    clean = {k: v for k, v in os.environ.items() if k not in _PROD_ENV}
    result = subprocess.run(
        [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        cwd=BACKEND,
        env={**clean, **_PROD_ENV, "DJANGO_SETTINGS_MODULE": "config.settings.prod"},
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# --- count-only and per-user lists: the tenant matrix looks for marker text and cannot see these


@pytest.mark.django_db
def test_the_timeseries_counts_only_the_callers_teams() -> None:
    from django.utils import timezone

    from apps.accounts.models import Membership
    from tests.factories import IncidentFactory

    service_a, service_b = ServiceFactory(), ServiceFactory()
    started = timezone.now() - timedelta(hours=2)
    IncidentFactory(service=service_a, triggered_at=started)
    IncidentFactory(service=service_a, triggered_at=started)
    IncidentFactory(service=service_b, triggered_at=started)

    def total_for(service) -> int:
        user = UserFactory()
        Membership.objects.create(user=user, team=service.team, role=Membership.Role.RESPONDER)
        client = APIClient()
        client.force_login(user)
        rows = client.get("/api/v1/analytics/timeseries/?tz=UTC").json()
        return sum(row["incidents"] for row in rows)

    assert total_for(service_a) == 2
    assert total_for(service_b) == 1


@pytest.mark.django_db
def test_the_session_list_holds_only_the_callers_own_sessions() -> None:
    from apps.security.models import SessionRecord

    mine, theirs = UserFactory(), UserFactory()
    SessionRecord.objects.create(session_key="theirs", user=theirs, ip="198.51.100.9")
    client = APIClient()
    client.force_login(mine)
    client.get("/api/v1/me/")  # a session of mine exists too
    SessionRecord.objects.create(session_key="mine-2", user=mine, ip="198.51.100.10")
    ips = {row["ip"] for row in client.get("/api/v1/me/sessions/").json()}
    assert "198.51.100.9" not in ips
    assert "198.51.100.10" in ips
