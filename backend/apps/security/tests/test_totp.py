"""TOTP pinned by the RFC test vectors, plus the replay and window rules we add on top."""

import base64

import pytest

from apps.security import totp

RFC_SECRET = base64.b32encode(b"12345678901234567890").decode()


@pytest.mark.parametrize(
    ("counter", "expected"),
    list(
        enumerate(
            [
                "755224",
                "287082",
                "359152",
                "969429",
                "338314",
                "254676",
                "287922",
                "162583",
                "399871",
                "520489",
            ]
        )
    ),
)
def test_hotp_matches_rfc_4226(counter: int, expected: str) -> None:
    assert totp.hotp(b"12345678901234567890", counter) == expected


@pytest.mark.parametrize(
    ("at", "expected"),
    [
        (59, "94287082"),
        (1111111109, "07081804"),
        (1111111111, "14050471"),
        (1234567890, "89005924"),
        (2000000000, "69279037"),
        (20000000000, "65353130"),
    ],
)
def test_totp_matches_rfc_6238_sha1(at: int, expected: str) -> None:
    assert totp.hotp(b"12345678901234567890", at // 30, digits=8) == expected


def test_a_code_is_accepted_within_one_step_of_drift_and_not_beyond() -> None:
    now = 1_700_000_000
    for drift in (-30, 0, 30):
        assert totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, now + drift), at=now) is not None
    for drift in (-90, 90):
        assert totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, now + drift), at=now) is None


def test_a_used_step_cannot_be_replayed() -> None:
    now = 1_700_000_000
    code = totp.code_at(RFC_SECRET, now)
    step = totp.verify(RFC_SECRET, code, at=now)
    assert step is not None
    assert totp.verify(RFC_SECRET, code, at=now, last_step=step) is None
    older = totp.code_at(RFC_SECRET, now - 30)
    assert totp.verify(RFC_SECRET, older, at=now, last_step=step) is None


@pytest.mark.parametrize("code", ["", "12345", "1234567", "abcdef", "12 34 5x"])
def test_malformed_codes_are_rejected(code: str) -> None:
    assert totp.verify(RFC_SECRET, code, at=1_700_000_000) is None


def test_the_provisioning_uri_is_what_authenticator_apps_read() -> None:
    uri = totp.provisioning_uri("JBSWY3DPEHPK3PXP", "ada@example.com")
    assert uri.startswith("otpauth://totp/Pulse%3Aada%40example.com?")
    assert "secret=JBSWY3DPEHPK3PXP" in uri
    assert "issuer=Pulse" in uri


def test_secrets_are_160_bits_and_unique() -> None:
    secrets = {totp.generate_secret() for _ in range(50)}
    assert len(secrets) == 50
    assert all(len(base64.b32decode(s + "=" * (-len(s) % 8))) == 20 for s in secrets)
