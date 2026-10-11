import time

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.security import totp
from apps.security.models import MfaDevice

PASSWORD = "correct horse battery staple 42"


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    cache.clear()


@pytest.fixture
def member(people):
    """A responder with a real (validated-strength) password."""
    user = people.on_call
    user.set_password(PASSWORD)
    user.save()
    return user


def login(client: APIClient, email: str, password: str = PASSWORD, **extra):
    return client.post(
        "/api/v1/auth/login/", {"email": email, "password": password}, format="json", **extra
    )


def enrol(client: APIClient) -> tuple[str, list[str]]:
    """Enrol MFA for the signed-in user. Returns (secret, backup codes)."""
    secret = client.post("/api/v1/me/mfa/setup/").json()["secret"]
    codes = client.post(
        "/api/v1/me/mfa/confirm/", {"code": totp.code_at(secret, time.time())}, format="json"
    )
    assert codes.status_code == 200, codes.content
    # Move past the step just used, so the next code is not refused as a replay.
    MfaDevice.objects.filter(secret=secret).update(last_used_step=int(time.time() // 30) - 2)
    return secret, codes.json()["backup_codes"]


def next_code(secret: str) -> str:
    device = MfaDevice.objects.get(secret=secret)
    step = max(int(time.time() // 30) - 1, device.last_used_step + 1)
    return totp.hotp(totp._key(secret), step)
