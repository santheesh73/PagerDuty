"""Guessing limits on the two sign-in steps hold for every caller.

Found by the final audit: the per-address limits skipped any caller that already had a session,
and code failures were only counted per password step. Someone signed in to any account who knew
a victim's password could repeat "password, five codes" without limit and guess the TOTP code.
"""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User

from .conftest import PASSWORD, enrol, login, next_code

pytestmark = pytest.mark.django_db


@pytest.fixture
def victim(people):
    """An account with MFA whose password the attacker knows."""
    user = User.objects.create_user("victim@example.test", PASSWORD, name="Victim")
    client = APIClient()
    assert login(client, user.email).status_code == 200
    secret, _codes = enrol(client)
    return user, secret


def _signed_in(member) -> APIClient:
    client = APIClient()
    # From another address, so signing in does not count toward the limit under test.
    assert login(client, member.email, REMOTE_ADDR="198.51.100.1").status_code == 200
    return client


def test_code_guesses_are_capped_per_account_across_password_steps(victim, settings) -> None:
    user, secret = victim
    client = APIClient()
    # A different address for every request, so only a per-account limit can stop this.
    addresses = (f"203.0.113.{n}" for n in range(1, 250))
    for _ in range(settings.MFA_LOCKOUT_FAILURES // 5):
        assert login(client, user.email, REMOTE_ADDR=next(addresses)).json() == {
            "mfa_required": True
        }
        for _ in range(5):
            wrong = client.post(
                "/api/v1/auth/mfa/", {"code": "000000"}, format="json", REMOTE_ADDR=next(addresses)
            )
            assert wrong.status_code == 401

    # Even the right password and the right code are refused until the lockout expires.
    login(client, user.email, REMOTE_ADDR=next(addresses))
    right = client.post(
        "/api/v1/auth/mfa/", {"code": next_code(secret)}, format="json", REMOTE_ADDR=next(addresses)
    )
    assert right.status_code == 429
    assert right.json()["error"]["code"] == "too_many_attempts"
    assert client.get("/api/v1/me/").status_code == 403


def test_a_correct_code_clears_the_count(victim, settings) -> None:
    user, secret = victim
    client = APIClient()
    addresses = (f"203.0.113.{n}" for n in range(1, 250))

    def step(code: str) -> int:
        login(client, user.email, REMOTE_ADDR=next(addresses))
        return client.post(
            "/api/v1/auth/mfa/", {"code": code}, format="json", REMOTE_ADDR=next(addresses)
        ).status_code

    assert [step("000000") for _ in range(settings.MFA_LOCKOUT_FAILURES - 1)] == [401] * (
        settings.MFA_LOCKOUT_FAILURES - 1
    )
    assert step(next_code(secret)) == 200
    client.post("/api/v1/auth/logout/", REMOTE_ADDR=next(addresses))
    # Counting starts again: the next wrong codes are ordinary failures, not a lockout.
    assert [step("000000") for _ in range(settings.MFA_LOCKOUT_FAILURES - 1)] == [401] * (
        settings.MFA_LOCKOUT_FAILURES - 1
    )


def test_a_signed_in_caller_is_still_limited_per_address_on_the_password_step(member) -> None:
    client = _signed_in(member)
    codes = [login(client, f"nobody{n}@example.test", "wrong").status_code for n in range(11)]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429


def test_a_signed_in_caller_is_still_limited_per_address_on_the_code_step(member) -> None:
    client = _signed_in(member)
    codes = [
        client.post("/api/v1/auth/mfa/", {"code": "000000"}, format="json").status_code
        for _ in range(11)
    ]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429
