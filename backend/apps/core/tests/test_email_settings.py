import importlib

import pytest

from config.settings import base

ENV = [
    "EMAIL_BACKEND",
    "EMAIL_HOST",
    "EMAIL_PORT",
    "EMAIL_USE_TLS",
    "EMAIL_USE_SSL",
    "EMAIL_HOST_USER",
    "EMAIL_HOST_PASSWORD",
    "EMAIL_TIMEOUT",
    "DEFAULT_FROM_EMAIL",
]


@pytest.fixture
def settings_with(monkeypatch):
    for name in ENV:
        monkeypatch.delenv(name, raising=False)

    def load(**env: str):
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        return importlib.reload(base)

    yield load
    for name in ENV:
        monkeypatch.delenv(name, raising=False)
    importlib.reload(base)


def test_without_any_email_setting_pages_go_to_the_console(settings_with) -> None:
    cfg = settings_with()
    assert cfg.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend"


def test_setting_a_host_selects_real_smtp_with_a_bounded_timeout(settings_with) -> None:
    cfg = settings_with(EMAIL_HOST="smtp.example.test", EMAIL_PORT="2525", EMAIL_USE_TLS="1")
    assert cfg.EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend"
    assert (cfg.EMAIL_HOST, cfg.EMAIL_PORT, cfg.EMAIL_USE_TLS) == ("smtp.example.test", 2525, True)
    # A blackholed SMTP host must not be able to pin a worker slot indefinitely.
    assert 0 < cfg.EMAIL_TIMEOUT <= 30


def test_credentials_and_sender_come_from_the_environment(settings_with) -> None:
    cfg = settings_with(
        EMAIL_HOST="smtp.example.test",
        EMAIL_HOST_USER="apikey",
        EMAIL_HOST_PASSWORD="s3cret",
        DEFAULT_FROM_EMAIL="pages@example.test",
        EMAIL_TIMEOUT="5",
    )
    assert (cfg.EMAIL_HOST_USER, cfg.EMAIL_HOST_PASSWORD) == ("apikey", "s3cret")
    assert cfg.DEFAULT_FROM_EMAIL == "pages@example.test"
    assert cfg.EMAIL_TIMEOUT == 5


def test_an_explicit_backend_wins_over_the_host(settings_with) -> None:
    cfg = settings_with(EMAIL_HOST="smtp.example.test", EMAIL_BACKEND="x.y.Backend")
    assert cfg.EMAIL_BACKEND == "x.y.Backend"
