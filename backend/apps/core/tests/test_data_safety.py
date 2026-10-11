"""Retention, database session limits, Celery limits and migration concurrency."""

import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest
import time_machine
from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import connection

from apps.alerting.models import Alert
from apps.core import retention
from apps.core.tasks import purge_old_data
from apps.incidents.models import Incident, IncidentEvent, Status
from apps.notifications.models import Notification
from tests.factories import (
    AlertFactory,
    IncidentEventFactory,
    IncidentFactory,
    NotificationFactory,
    ServiceFactory,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
BACKEND = Path(__file__).resolve().parents[3]


def _resolved(days_ago: int, service=None):
    service = service or ServiceFactory()
    return IncidentFactory(
        service=service,
        status=Status.RESOLVED,
        resolved_at=NOW - timedelta(days=days_ago),
        triggered_at=NOW - timedelta(days=days_ago, hours=1),
    )


# --- retention -------------------------------------------------------------------------------


@pytest.mark.django_db
def test_retention_is_off_by_default_and_for_zero(settings) -> None:
    assert settings.RETENTION_DAYS == 0
    _resolved(900)
    assert retention.purge(0, now=NOW) == {"incidents": 0, "alerts": 0}
    assert purge_old_data() == {"incidents": 0, "alerts": 0}
    assert Incident.objects.count() == 1


@pytest.mark.django_db
def test_retention_removes_old_resolved_incidents_with_everything_attached(settings) -> None:
    old, recent = _resolved(100), _resolved(10)
    open_but_ancient = IncidentFactory(
        status=Status.TRIGGERED, triggered_at=NOW - timedelta(days=500)
    )
    for incident in (old, recent, open_but_ancient):
        AlertFactory(service=incident.service, incident=incident)
        NotificationFactory(incident=incident)
        IncidentEventFactory(incident=incident)
    AlertFactory(incident=None, received_at=NOW - timedelta(days=100))  # never joined one
    AlertFactory(incident=None, received_at=NOW - timedelta(days=1))

    with time_machine.travel(NOW, tick=False):
        result = retention.purge(30, now=NOW)

    assert result["incidents"] == 1
    assert set(Incident.objects.values_list("pk", flat=True)) == {recent.pk, open_but_ancient.pk}
    assert not Alert.objects.filter(incident_id=old.pk).exists()
    assert not Notification.objects.filter(incident_id=old.pk).exists()
    assert not IncidentEvent.objects.filter(incident_id=old.pk).exists()
    assert Alert.objects.filter(incident_id=recent.pk).exists()
    assert Alert.objects.filter(incident__isnull=True).count() == 1  # only the recent orphan
    assert Alert.objects.filter(incident_id=open_but_ancient.pk).exists()


@pytest.mark.django_db
def test_retention_works_through_more_than_one_batch(monkeypatch) -> None:
    monkeypatch.setattr(retention, "BATCH", 3)
    service = ServiceFactory()
    for _ in range(8):
        _resolved(100, service)
    assert retention.purge(30, now=NOW)["incidents"] == 8
    assert Incident.objects.count() == 0


@pytest.mark.django_db
def test_the_daily_task_purges_per_the_setting_and_clears_expired_sessions(settings) -> None:
    settings.RETENTION_DAYS = 30
    _resolved(100)
    Session.objects.create(session_key="old", session_data="x", expire_date=NOW - timedelta(days=1))
    Session.objects.create(session_key="new", session_data="x", expire_date=NOW + timedelta(days=1))
    with time_machine.travel(NOW, tick=False):
        assert purge_old_data()["incidents"] == 1
    assert list(Session.objects.values_list("session_key", flat=True)) == ["new"]


def test_the_purge_is_scheduled_daily() -> None:
    entry = settings.CELERY_BEAT_SCHEDULE["purge-old-data"]
    assert entry["task"] == "apps.core.tasks.purge_old_data"
    assert entry["schedule"] == timedelta(hours=24)


# --- limits that stop one bad thing wedging the system -----------------------------------------


@pytest.mark.django_db
def test_database_sessions_carry_statement_and_lock_timeouts() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SHOW statement_timeout")
        assert cursor.fetchone() == ("15s",)
        cursor.execute("SHOW lock_timeout")
        assert cursor.fetchone() == ("5s",)


@pytest.mark.django_db
def test_a_runaway_query_is_cancelled_by_the_statement_timeout() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL statement_timeout = 200")
        with pytest.raises(Exception, match="statement timeout"):
            cursor.execute("SELECT pg_sleep(5)")


def test_session_options_can_be_disabled_for_poolers(monkeypatch) -> None:
    from config.settings import base

    assert "statement_timeout=15000" in base._db_session_options()
    for name in ("DB_STATEMENT_TIMEOUT_MS", "DB_LOCK_TIMEOUT_MS", "DB_IDLE_IN_TX_TIMEOUT_MS"):
        monkeypatch.setenv(name, "0")
    assert base._db_session_options() == ""


def test_celery_is_configured_to_survive_a_dead_or_wedged_worker() -> None:
    assert settings.CELERY_TASK_ACKS_LATE is True
    assert settings.CELERY_TASK_REJECT_ON_WORKER_LOST is True
    assert settings.CELERY_WORKER_PREFETCH_MULTIPLIER == 1
    assert settings.CELERY_BROKER_TRANSPORT_OPTIONS["visibility_timeout"] == 3600
    assert settings.CELERY_TASK_SOFT_TIME_LIMIT < settings.CELERY_TASK_TIME_LIMIT


# --- concurrent migrate ----------------------------------------------------------------------


def _admin_url(name: str) -> str:
    base = settings.DATABASES["default"]
    return (
        f"postgres://{base['USER']}:{base['PASSWORD']}@{base['HOST']}:{base['PORT'] or 5432}/{name}"
    )


def test_concurrent_migrate_safely_on_a_fresh_database_all_succeed() -> None:
    name = f"pulse_race_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(_admin_url("postgres"), autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    try:
        env = {
            **os.environ,
            "DATABASE_URL": _admin_url(name),
            "DJANGO_SETTINGS_MODULE": "config.settings.dev",
            "DB_STATEMENT_TIMEOUT_MS": "0",
        }
        procs = [
            subprocess.Popen(
                [sys.executable, "manage.py", "migrate_safely"],
                cwd=BACKEND,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            for _ in range(4)
        ]
        outputs = [p.communicate(timeout=240)[0] for p in procs]
        codes = [p.returncode for p in procs]
        assert codes == [0, 0, 0, 0], "\n---\n".join(outputs)

        check = subprocess.run(
            [sys.executable, "manage.py", "migrate", "--check"],
            cwd=BACKEND,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert check.returncode == 0, check.stdout + check.stderr
    finally:
        with psycopg.connect(_admin_url("postgres"), autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
