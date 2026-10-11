"""A fake Twilio and a fake webhook receiver: real local HTTP servers, never the real services."""

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

import pytest
from django.utils import timezone

from apps.notifications.models import UserContact
from conftest import Paging


@dataclass
class Recorded:
    path: str
    form: dict[str, str]
    headers: dict[str, str]
    body: bytes = b""


@dataclass
class FakeServer:
    """Answers every POST from a script of (status, body) pairs; the last one repeats."""

    script: list[tuple[int, dict | bytes]] = field(default_factory=lambda: [(201, {"sid": "SM1"})])
    requests: list[Recorded] = field(default_factory=list)
    server: HTTPServer | None = None
    counter: int = 0

    @property
    def url(self) -> str:
        assert self.server is not None
        return f"http://127.0.0.1:{self.server.server_port}"

    def start(self) -> "FakeServer":
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length)
                outer.counter += 1
                form = {k: v[0] for k, v in parse_qs(raw.decode(errors="replace")).items()}
                outer.requests.append(Recorded(self.path, form, dict(self.headers), raw))
                index = min(outer.counter - 1, len(outer.script) - 1)
                status, payload = outer.script[index]
                if isinstance(payload, dict):
                    payload = {**payload, "sid": f"{payload.get('sid', 'SM')}-{outer.counter}"}
                    payload = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args: object) -> None:
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()


@pytest.fixture
def twilio(settings):
    fake = FakeServer().start()
    settings.TWILIO_ACCOUNT_SID = "ACtest"
    settings.TWILIO_AUTH_TOKEN = "twilio-test-token"
    settings.TWILIO_FROM_NUMBER = "+15005550006"
    settings.TWILIO_API_BASE = fake.url
    settings.PUBLIC_BASE_URL = "https://pulse.test"
    yield fake
    fake.stop()


@pytest.fixture
def receiver(settings):
    fake = FakeServer(script=[(200, b"ok")]).start()
    settings.WEBHOOK_ALLOW_PRIVATE = True
    yield fake
    fake.stop()


@pytest.fixture
def contact(people: Paging) -> UserContact:
    """The on-call person, with a verified phone and a webhook configured."""
    return UserContact.objects.create(
        user=people.on_call,
        phone_number="+14155550123",
        phone_verified_at=timezone.now(),
        webhook_url="https://hooks.example.com/services/T000/B000/secret",
        webhook_secret="whsec-test-secret",
    )
