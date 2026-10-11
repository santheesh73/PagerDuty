"""The SSRF guard. Every case here is a way a user-supplied URL could reach something internal."""

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from apps.core import safe_http
from apps.core.safe_http import TransportError, UnsafeURL, post_json, validate_url


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/hook",  # not https
        "ftp://example.com/hook",
        "file:///etc/passwd",
        "https://user:pass@example.com/hook",  # credentials
        "https://example.com:8443/hook",  # not 443
        "https:///nohost",
        "https://[::1]/hook",  # loopback v6
        "https://127.0.0.1/hook",
        "https://127.1/hook",  # short form of loopback
        "https://2130706433/hook",  # decimal loopback
        "https://0x7f000001/hook",  # hex loopback
        "https://0.0.0.0/hook",
        "https://10.0.0.5/hook",
        "https://172.16.0.1/hook",
        "https://192.168.1.1/hook",
        "https://169.254.169.254/latest/meta-data/",  # cloud metadata
        "https://100.64.0.1/hook",  # CGNAT
        "https://[::ffff:127.0.0.1]/hook",  # v4-mapped loopback
        "https://[::ffff:169.254.169.254]/hook",
        "https://[fe80::1]/hook",
        "https://[fc00::1]/hook",
        "https://localhost/hook",
        "https://224.0.0.1/hook",  # multicast
    ],
)
def test_internal_and_malformed_urls_are_refused(url: str) -> None:
    def check() -> None:
        host, port = validate_url(url, resolve=False)
        safe_http.resolve_public(host, port)

    with pytest.raises(UnsafeURL):
        check()


def test_a_name_with_any_internal_answer_is_refused(monkeypatch) -> None:
    def fake_getaddrinfo(host, port, **_):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", port)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeURL):
        safe_http.resolve_public("rebind.example", 443)


def test_a_public_address_is_accepted(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, **_: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))
        ],
    )
    assert safe_http.resolve_public("example.com", 443) == "93.184.216.34"


def test_post_connects_to_the_validated_address_not_a_fresh_lookup(monkeypatch) -> None:
    """DNS rebinding: the name resolves publicly for the check; the socket must use that IP."""
    connected: list[tuple] = []
    answers = iter(["93.184.216.34", "127.0.0.1"])  # second lookup would be the rebind

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, **_: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (next(answers), port))
        ],
    )

    def fake_create_connection(address, timeout=None, **_):
        connected.append(address)
        raise OSError("stop here")

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)
    with pytest.raises(TransportError):
        post_json("https://hooks.example.com/x", {"a": 1})
    assert connected == [("93.184.216.34", 443)]


class _Receiver:
    def __init__(self, status: int = 200, location: str | None = None, body: bytes = b"ok") -> None:
        outer = self
        self.requests: list[dict] = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", 0))
                outer.requests.append(
                    {
                        "path": self.path,
                        "headers": dict(self.headers),
                        "body": self.rfile.read(length),
                    }
                )
                self.send_response(status)
                if location:
                    self.send_header("Location", location)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: object) -> None:
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/hook?x=1"

    def close(self) -> None:
        self.server.shutdown()


def test_private_targets_are_refused_unless_a_test_opts_in() -> None:
    receiver = _Receiver()
    try:
        with pytest.raises(UnsafeURL):
            post_json(receiver.url, {"a": 1})
        assert receiver.requests == [], "the request must not even have been sent"
        response = post_json(receiver.url, {"a": 1}, allow_private=True)
        assert response.status == 200
        assert json.loads(receiver.requests[0]["body"]) == {"a": 1}
        assert receiver.requests[0]["path"] == "/hook?x=1"
    finally:
        receiver.close()


def test_redirects_are_never_followed() -> None:
    target = _Receiver()
    redirector = _Receiver(status=302, location=target.url)
    try:
        response = post_json(redirector.url, {}, allow_private=True)
        assert response.status == 302
        assert target.requests == [], "a redirect to an internal address must not be followed"
    finally:
        target.close()
        redirector.close()


def test_the_response_body_is_capped() -> None:
    receiver = _Receiver(body=b"x" * (safe_http.MAX_RESPONSE_BYTES * 3))
    try:
        assert (
            len(post_json(receiver.url, {}, allow_private=True).body)
            == safe_http.MAX_RESPONSE_BYTES
        )
    finally:
        receiver.close()


def test_network_errors_are_transport_errors() -> None:
    with pytest.raises(TransportError):
        post_json("http://127.0.0.1:1/x", {}, allow_private=True, timeout=1)
