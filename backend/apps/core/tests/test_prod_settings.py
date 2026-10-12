"""Production settings refuse to boot with an unsafe configuration."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[3]
SAFE = {
    "SECRET_KEY": "x" * 50,
    "ALLOWED_HOSTS": "pulse.example.test",
    "DATABASE_URL": "postgres://pulse:pulse@localhost:5432/pulse",
    "NUM_PROXIES": "1",
}


def _load(
    env: dict[str, str], code: str = "import config.settings.prod"
) -> subprocess.CompletedProcess[str]:
    clean = {k: v for k, v in os.environ.items() if k not in SAFE and k != "API_DOCS"}
    return subprocess.run(  # noqa: S603 (the interpreter running this test, fixed arguments)
        [sys.executable, "-c", code],
        cwd=BACKEND,
        env={**clean, **env},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def test_a_complete_configuration_loads() -> None:
    assert _load(SAFE).returncode == 0


@pytest.mark.parametrize("missing", sorted(SAFE))
def test_each_required_setting_is_enforced(missing: str) -> None:
    result = _load({k: v for k, v in SAFE.items() if k != missing})
    assert result.returncode != 0
    assert f"{missing} must be set in production" in result.stderr


def test_no_proxies_in_front_is_a_valid_answer() -> None:
    # "0" is falsy as a number but a deliberate setting: nothing in front of the app.
    assert _load({**SAFE, "NUM_PROXIES": "0"}).returncode == 0


def _setting(name: str, env: dict[str, str]) -> str:
    result = _load(env, f"import config.settings.prod as s; print(s.{name})")
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_swagger_ui_is_off_in_production_unless_asked_for() -> None:
    # It loads script from a CDN onto the origin that holds the session cookie.
    assert _setting("API_DOCS", SAFE) == "False"
    assert _setting("API_DOCS", {**SAFE, "API_DOCS": "1"}) == "True"
