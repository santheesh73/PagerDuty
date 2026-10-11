"""Sentry error reporting: off unless `SENTRY_DSN` is set, and scrubbed before it leaves.

Pulse handles integration keys, session cookies and passwords, so nothing is sent as-is:
`send_default_pii` stays off, request bodies/cookies/headers are dropped or redacted, local
variables are not attached to stack frames, and `scrub` walks whatever is left redacting any
key that looks like a secret.
"""

import re
from typing import Any

REDACTED = "[Filtered]"
# Matched against dict keys (case-insensitive, substring) anywhere in an event.
_SECRET_KEY = re.compile(
    r"pass|secret|token|authorization|cookie|csrf|session|api[-_]?key|routing[-_]?key|"
    r"integration|credential|signature|dsn",
    re.IGNORECASE,
)
_DROP_HEADERS = {"authorization", "cookie", "x-csrftoken", "set-cookie", "x-tick-secret"}


def scrub(value: Any) -> Any:
    """Recursively redact the values of secret-looking keys; leaves other data untouched."""
    if isinstance(value, dict):
        return {
            k: (REDACTED if isinstance(k, str) and _SECRET_KEY.search(k) else scrub(v))
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [scrub(v) for v in value]
    return value


def before_send(event: dict[str, Any], hint: dict[str, Any] | None = None) -> dict[str, Any]:
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("cookies", None)
        request.pop("data", None)  # Events API bodies carry the routing key; logins the password
        request.pop("query_string", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {
                k: v for k, v in headers.items() if str(k).lower() not in _DROP_HEADERS
            }
    event.pop("user", None)
    return scrub(event)  # type: ignore[no-any-return,unused-ignore]


def init(dsn: str, *, environment: str, release: str | None, traces_sample_rate: float) -> None:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        integrations=[DjangoIntegration(), CeleryIntegration(), RedisIntegration()],
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        traces_sample_rate=traces_sample_rate,
        before_send=before_send,  # type: ignore[arg-type]
        before_breadcrumb=lambda crumb, hint: scrub(crumb),
    )
