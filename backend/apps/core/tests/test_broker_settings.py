"""Settings that keep a sick dependency from taking the API down with it."""

import importlib

import pytest
from django.conf import settings


def test_a_hung_broker_cannot_block_a_request_for_long() -> None:
    options = settings.CELERY_BROKER_TRANSPORT_OPTIONS
    assert 0 < options["socket_connect_timeout"] <= 5
    assert 0 < options["socket_timeout"] <= 10
    policy = settings.CELERY_TASK_PUBLISH_RETRY_POLICY
    assert policy["max_retries"] <= 1


def test_the_demo_cache_never_culls_its_counters(monkeypatch: pytest.MonkeyPatch) -> None:
    from config.settings import base

    monkeypatch.setenv("DEMO_MODE", "1")
    try:
        cache = importlib.reload(base).CACHES["default"]
        assert cache["BACKEND"].endswith("DatabaseCache")
        assert cache["OPTIONS"]["MAX_ENTRIES"] >= 100_000
    finally:
        monkeypatch.delenv("DEMO_MODE")
        importlib.reload(base)
