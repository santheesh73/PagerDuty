"""TOTP (RFC 6238, SHA-1, 6 digits, 30 s), the format every authenticator app speaks.

Implemented here rather than pulled in as a dependency because it is twenty lines of stdlib HMAC,
and the RFC's own test vectors (tests/test_totp.py) pin it.
"""

import base64
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

STEP = 30
DIGITS = 6
WINDOW = 1  # accept the previous and next 30 s step, for clock drift between phone and server


def generate_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    return base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)


def hotp(key: bytes, counter: int, digits: int = DIGITS, digest: str = "sha1") -> str:
    mac = hmac.new(key, struct.pack(">Q", counter), digest).digest()
    offset = mac[-1] & 0x0F
    value = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**digits).zfill(digits)


def code_at(secret: str, at: float) -> str:
    return hotp(_key(secret), int(at // STEP))


def verify(secret: str, code: str, *, at: float | None = None, last_step: int = 0) -> int | None:
    """The time step `code` matches, or None. A step at or before `last_step` is refused, so a
    code that was already used (or an older one) cannot be replayed."""
    code = code.strip().replace(" ", "")
    if not (code.isdigit() and len(code) == DIGITS):
        return None
    now_step = int((time.time() if at is None else at) // STEP)
    key = _key(secret)
    for step in range(now_step - WINDOW, now_step + WINDOW + 1):
        if step > last_step and hmac.compare_digest(hotp(key, step), code):
            return step
    return None


def provisioning_uri(secret: str, account: str, issuer: str = "Pulse") -> str:
    label = quote(f"{issuer}:{account}")
    query = urlencode(
        {"secret": secret, "issuer": issuer, "algorithm": "SHA1", "digits": DIGITS, "period": STEP}
    )
    return f"otpauth://totp/{label}?{query}"
