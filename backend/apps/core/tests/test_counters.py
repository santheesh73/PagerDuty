"""Fixed-window counters (rate limits, the sign-in lockout, the password-reset cap) reset on time
whatever the cache backend does with expiry.

Redis keeps a key's TTL on INCR, but Django's database cache, which demo mode uses, implements
`incr` as get-then-set, which resets the expiry to the default 300 s every time. A counter that
relied on the TTL set by `add` therefore never closed its window under steady traffic: the
one-minute tick limit became permanent, and the 15-minute lockout could shrink to 5 minutes.
"""

from datetime import timedelta
from unittest import mock

import pytest
import time_machine
from django.core.cache import cache
from django.core.management import call_command
from django.test import RequestFactory

from apps.accounts import views as account_views
from apps.core import ratelimit
from conftest import T0

pytestmark = pytest.mark.django_db

DB_CACHE = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "t"}}
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@pytest.fixture(params=["database", "locmem"])
def backend(request, settings):  # type: ignore[no-untyped-def]
    settings.CACHES = DB_CACHE if request.param == "database" else LOCMEM
    if request.param == "database":
        call_command("createcachetable", verbosity=0)
    cache.clear()
    return request.param


def test_a_rate_limit_window_closes_on_time(backend: str) -> None:
    request = RequestFactory().post("/x", REMOTE_ADDR="203.0.113.5")
    with time_machine.travel(T0, tick=False) as clock:
        assert [ratelimit.allow("t", request, limit=2) for _ in range(3)] == [True, True, False]
        clock.shift(timedelta(seconds=30))
        assert ratelimit.allow("t", request, limit=2) is False, "still inside the window"
        clock.shift(timedelta(seconds=31))
        assert ratelimit.allow("t", request, limit=2) is True, "a new window, on any backend"


def test_steady_traffic_does_not_hold_a_window_open(backend: str) -> None:
    request = RequestFactory().post("/x", REMOTE_ADDR="203.0.113.6")
    allowed = []
    with time_machine.travel(T0, tick=False) as clock:
        for _ in range(30):  # one call every 6 s for three minutes, limit 12 a minute
            allowed.append(ratelimit.allow("tick", request, limit=12))
            clock.shift(timedelta(seconds=6))
    assert all(allowed), "10 calls a minute never trip a 12-a-minute limit"


def test_the_sign_in_lockout_lasts_its_configured_time(backend: str, settings) -> None:
    settings.LOGIN_LOCKOUT_FAILURES, settings.LOGIN_LOCKOUT_SECONDS = 3, 900
    with time_machine.travel(T0, tick=False) as clock:
        for _ in range(3):
            account_views._count_failure("victim@example.com")
        assert account_views._locked_out("victim@example.com")
        clock.shift(timedelta(minutes=6))
        assert account_views._locked_out("victim@example.com"), "not cut short at 5 minutes"
        clock.shift(timedelta(minutes=10))
        assert not account_views._locked_out("victim@example.com")


def test_the_lockout_runs_from_the_first_failure_not_a_clock_boundary(
    backend: str, settings
) -> None:
    settings.LOGIN_LOCKOUT_FAILURES, settings.LOGIN_LOCKOUT_SECONDS = 3, 900
    with time_machine.travel(T0 + timedelta(minutes=14), tick=False) as clock:
        for _ in range(3):
            account_views._count_failure("victim@example.com")
        clock.shift(timedelta(minutes=2))  # past any quarter-hour boundary
        assert account_views._locked_out("victim@example.com")
        clock.shift(timedelta(minutes=14))
        assert not account_views._locked_out("victim@example.com")


def test_a_successful_sign_in_clears_the_lockout_count(backend: str, settings) -> None:
    settings.LOGIN_LOCKOUT_FAILURES = 3
    with time_machine.travel(T0, tick=False):
        for _ in range(2):
            account_views._count_failure("ada@example.com")
        account_views._clear_failures("ada@example.com")
        account_views._count_failure("ada@example.com")
        assert not account_views._locked_out("ada@example.com")


def test_counters_fail_open_when_the_cache_is_down() -> None:
    request = RequestFactory().post("/x", REMOTE_ADDR="203.0.113.7")
    with mock.patch.object(ratelimit.cache, "add", side_effect=ConnectionError("down")):
        assert ratelimit.allow("t", request, limit=0) is True
