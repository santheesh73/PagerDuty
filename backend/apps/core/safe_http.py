"""Outbound HTTPS for URLs a *user* supplied (webhook destinations), without SSRF.

A user-controlled URL is an invitation to make the server call something it should not: the
cloud metadata service (169.254.169.254), localhost admin ports, the database, other tenants'
internal services. The defences, in the order they bite:

* https only, no credentials in the URL, port 443 only;
* the hostname is resolved here, and **every** address it resolves to must be public (not
  loopback, private, link-local, CGNAT, multicast, reserved or unspecified, including IPv4
  addresses wrapped in IPv6), so a name with one public and one internal record is refused;
* the connection is made to the address we validated, not re-resolved by the socket layer, so a
  DNS answer that changes between "check" and "connect" (rebinding) cannot redirect us;
* TLS is verified against the original hostname;
* redirects are never followed (a public URL answering 302 to http://169.254.169.254/ is a
  classic bypass), and the response body is capped.

`allow_private=True` exists for tests against a local fake receiver and is wired to a setting that
is off everywhere else.
"""

import contextlib
import ipaddress
import json
import socket
import ssl
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPSConnection
from typing import Any
from urllib.parse import urlsplit

MAX_RESPONSE_BYTES = 64 * 1024
DEFAULT_TIMEOUT = 8.0


class UnsafeURL(ValueError):
    """The URL points somewhere we refuse to connect to (message is safe to show the user)."""


class TransportError(OSError):
    """Network-level failure (DNS, connect, TLS, timeout): worth retrying."""


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes


_CGNAT = ipaddress.ip_network("100.64.0.0/10")


def _is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if isinstance(address, ipaddress.IPv6Address) and address.sixtofour is not None:
        return _is_public(address.sixtofour)
    if address in _CGNAT:
        return False
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or not address.is_global
    )


def resolve_public(host: str, port: int, *, allow_private: bool = False) -> str:
    """The IP to connect to for `host`, refusing the name if any answer is not public."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise TransportError(f"cannot resolve {host}") from exc
    addresses = []
    for info in infos:
        address = ipaddress.ip_address(str(info[4][0]).split("%")[0])
        if not allow_private and not _is_public(address):
            raise UnsafeURL("The address this URL points to is not allowed.")
        addresses.append(str(address))
    if not addresses:
        raise TransportError(f"no addresses for {host}")
    return addresses[0]


def validate_url(url: str, *, allow_private: bool = False, resolve: bool = True) -> tuple[str, int]:
    """Raise UnsafeURL unless `url` is a public https URL. Returns (host, port)."""
    parts = urlsplit(url)
    scheme_ok = parts.scheme == "https" or (allow_private and parts.scheme == "http")
    if not scheme_ok:
        raise UnsafeURL("Only https URLs are allowed.")
    if not parts.hostname:
        raise UnsafeURL("The URL has no host.")
    if parts.username is not None or parts.password is not None:
        raise UnsafeURL("Credentials in the URL are not allowed.")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise UnsafeURL("The URL has an invalid port.") from exc
    if not allow_private and port != 443:
        raise UnsafeURL("Only port 443 is allowed.")
    if resolve:
        # Unresolvable right now is not unsafe; send-time resolution decides.
        with contextlib.suppress(TransportError):
            resolve_public(parts.hostname, port, allow_private=allow_private)
    return parts.hostname, port


class _PinnedHTTPSConnection(HTTPSConnection):
    """HTTPS to a pre-validated IP, with SNI and certificate checks for the real hostname."""

    def __init__(self, host: str, ip: str, port: int, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self) -> None:
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        context: ssl.SSLContext = self._context  # type: ignore[attr-defined]
        self.sock = context.wrap_socket(sock, server_hostname=self.host)


class _PinnedHTTPConnection(HTTPConnection):
    def __init__(self, host: str, ip: str, port: int, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout)
        self._ip = ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


def post_bytes(
    url: str,
    body: bytes,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    allow_private: bool = False,
) -> Response:
    """POST raw bytes (so a caller can sign exactly what is sent). Never follows redirects."""
    host, port = validate_url(url, allow_private=allow_private, resolve=False)
    ip = resolve_public(host, port, allow_private=allow_private)
    parts = urlsplit(url)
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    connection_class = _PinnedHTTPSConnection if parts.scheme == "https" else _PinnedHTTPConnection
    connection = connection_class(host, ip, port, timeout)
    try:
        connection.request(
            "POST",
            path,
            body=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "pulse-webhook",
                **(headers or {}),
            },
        )
        response = connection.getresponse()
        return Response(response.status, response.read(MAX_RESPONSE_BYTES))
    except (OSError, ssl.SSLError) as exc:
        raise TransportError(f"{type(exc).__name__}: {exc}") from exc
    finally:
        connection.close()


def post_json(url: str, payload: Any, **kwargs: Any) -> Response:
    return post_bytes(url, json.dumps(payload, separators=(",", ":")).encode(), **kwargs)
