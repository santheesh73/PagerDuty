"""ops/alerts.yml and the Grafana dashboard may only reference metrics /metrics really exposes.

A renamed or removed metric would otherwise leave an alert that can never fire, which is the
worst way for an alerting rule to fail. promtool (run in CI) checks the *syntax*; this checks
the *names*.
"""

import json
import re
from pathlib import Path

import pytest
import yaml
from django.test import Client
from django.utils import timezone

from apps.core import heartbeat
from tests.factories import NotificationFactory, ServiceFactory

pytestmark = pytest.mark.django_db

OPS = Path(__file__).resolve().parents[4] / "ops"
PAYLOAD = {"summary": "x", "severity": "critical", "source": "t"}
SUFFIXES = ("_bucket", "_count", "_sum", "_total", "_created")


def _exposed(settings) -> set[str]:
    settings.METRICS_TOKEN = "t"
    service = ServiceFactory()
    client = Client()
    for key in (service.integration_key, "z" * 32):  # one accepted, one rejected
        client.post(
            "/api/v1/events/",
            {"routing_key": key, "event_action": "trigger", "payload": PAYLOAD},
            content_type="application/json",
        )
    NotificationFactory(status="sent", sent_at=timezone.now())
    heartbeat.record()
    body = client.get("/metrics", headers={"Authorization": "Bearer t"}).content.decode()
    return {m.group(1) for m in re.finditer(r"^(pulse_\w+)[{ ]", body, re.MULTILINE)}


def _metrics_in(expr: str) -> set[str]:
    return set(re.findall(r"\bpulse_\w+", expr))


def _base(name: str) -> str:
    for suffix in SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _check(exprs: list[str], exposed: set[str]) -> None:
    bases = {_base(n) for n in exposed} | exposed
    for expr in exprs:
        for name in _metrics_in(expr):
            assert name in exposed or _base(name) in bases, f"{name!r} is not exposed: {expr}"


@pytest.mark.skipif(not OPS.exists(), reason="ops/ is not part of the backend image")
def test_alert_rules_only_use_exposed_metrics(settings) -> None:
    exposed = _exposed(settings)
    rules = yaml.safe_load((OPS / "alerts.yml").read_text())["groups"]
    exprs = [r["expr"] for g in rules for r in g["rules"]]
    assert len(exprs) >= 10
    _check(exprs, exposed)


@pytest.mark.skipif(not OPS.exists(), reason="ops/ is not part of the backend image")
def test_dashboard_only_uses_exposed_metrics(settings) -> None:
    exposed = _exposed(settings)
    dashboard = json.loads((OPS / "grafana" / "pulse.json").read_text())
    exprs = [t["expr"] for p in dashboard["panels"] for t in p["targets"]]
    assert len(exprs) >= 15
    _check(exprs, exposed)


@pytest.mark.skipif(not OPS.exists(), reason="ops/ is not part of the backend image")
def test_every_alert_has_a_severity_and_summary() -> None:
    for group in yaml.safe_load((OPS / "alerts.yml").read_text())["groups"]:
        for rule in group["rules"]:
            assert rule["labels"]["severity"] in {"critical", "warning"}, rule["alert"]
            assert rule["annotations"]["summary"], rule["alert"]
