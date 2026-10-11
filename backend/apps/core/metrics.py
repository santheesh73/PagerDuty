"""Prometheus metrics.

Two kinds, chosen so the numbers stay right with several gunicorn workers and separate
Celery containers:

* **State metrics** (incidents, notifications, escalation lag, queue depth) are computed from
  Postgres/Redis at scrape time by `StateCollector`. The database is the source of truth, so
  every process and every restart sees the same value, and nothing here can drift.
* **Request metrics** (HTTP rate/latency/5xx, Events API results) are counted in-process. Under
  gunicorn they are aggregated across workers with prometheus_client's multiprocess mode
  (`PROMETHEUS_MULTIPROC_DIR`, set by the container entrypoint).
"""

import logging
import os
import re
import time
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db.models import Count, F, Q, Sum
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)
from prometheus_client.core import (
    CounterMetricFamily,
    GaugeMetricFamily,
    HistogramMetricFamily,
    Metric,
)

from . import heartbeat, selfcheck

logger = logging.getLogger(__name__)

HTTP_REQUESTS = Counter("pulse_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram(
    "pulse_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
INGEST_REQUESTS = Counter(
    "pulse_ingest_requests_total",
    "Events API requests by outcome (accepted, ignored, or rejected_<http status>)",
    ["result"],
)
INGEST_LATENCY = Histogram(
    "pulse_ingest_latency_seconds",
    "Events API request latency",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)

DELIVERY_BUCKETS = (1, 5, 15, 30, 60, 120, 300)
QUEUES = ("escalations", "notifications", "default")
_WORKERS_TTL = 30.0
_workers: tuple[float, int | None] = (0.0, None)


def _worker_count() -> int | None:
    """Live Celery workers, via a broker round trip; cached because `ping` blocks ~1 s."""
    global _workers
    stamp, value = _workers
    if time.monotonic() - stamp < _WORKERS_TTL:
        return value
    try:
        from config.celery import app

        value = len(app.control.inspect(timeout=1).ping() or {})
    except Exception:
        value = None
    _workers = (time.monotonic(), value)
    return value


def _queue_depths() -> dict[str, int] | None:
    from redis import Redis

    try:
        client = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
        return {q: int(client.llen(q)) for q in QUEUES}  # type: ignore[arg-type]
    except Exception:
        return None


class StateCollector:
    """Metrics derived from the database/broker at scrape time."""

    def collect(self) -> Iterator[Metric]:
        now = timezone.now()
        try:
            yield from self._database(now)
        except Exception:
            logger.exception("metrics: database collection failed")
        yield from self._celery(now)

    def _database(self, now) -> Iterator[Metric]:
        from apps.incidents.models import Incident, Status
        from apps.notifications.models import Notification

        # `severity` is the incident's urgency (high|low), which is derived from the alert
        # severity when the incident opens.
        open_ = GaugeMetricFamily(
            "pulse_incidents_open", "Open incidents by severity", labels=["severity"]
        )
        counts = dict(
            Incident.objects.exclude(status=Status.RESOLVED)
            .values_list("urgency")
            .annotate(n=Count("id"))
            .values_list("urgency", "n")
        )
        from apps.incidents.models import Urgency

        for urgency in Urgency.values:
            open_.add_metric([urgency], counts.get(urgency, 0))
        yield open_

        yield CounterMetricFamily(
            "pulse_incidents_triggered", "Incidents opened", value=Incident.objects.count()
        )
        yield CounterMetricFamily(
            "pulse_incidents_resolved",
            "Incidents resolved",
            value=Incident.objects.filter(status=Status.RESOLVED).count(),
        )
        yield GaugeMetricFamily(
            "pulse_escalation_sweeper_lag_seconds",
            "Age of the most overdue escalation timer (0 when none is due)",
            value=selfcheck.sweeper_lag_seconds(now),
        )
        yield GaugeMetricFamily(
            "pulse_escalations_overdue",
            "Triggered incidents whose escalation timer has expired",
            value=selfcheck.overdue_escalations(now),
        )

        # Only terminal states are a counter: `pending` goes down when a page is delivered,
        # which would look like a counter reset.
        terminal = [s for s in Notification.Status.values if s != Notification.Status.PENDING]
        totals = CounterMetricFamily(
            "pulse_notifications",
            "Notifications by channel and outcome",
            labels=["channel", "status"],
        )
        grouped = {
            (c, s): n
            for c, s, n in Notification.objects.values_list("channel", "status")
            .annotate(n=Count("id"))
            .values_list("channel", "status", "n")
        }
        for channel in Notification.Channel.values:
            for status in terminal:
                totals.add_metric([channel, status], grouped.get((channel, status), 0))
        yield totals
        yield GaugeMetricFamily(
            "pulse_notifications_pending",
            "Notifications created but not yet delivered",
            value=Notification.objects.filter(status=Notification.Status.PENDING).count(),
        )
        yield GaugeMetricFamily(
            "pulse_notifications_stuck",
            "Pending notifications older than 5 minutes (redelivery is not working)",
            value=selfcheck.stuck_notifications(now),
        )
        yield self._delivery_histogram()

    @staticmethod
    def _delivery_histogram() -> Metric:
        from apps.notifications.models import Notification

        histogram = HistogramMetricFamily(
            "pulse_notification_delivery_seconds",
            "Seconds from a page being created to it being sent",
            labels=["channel"],
        )
        delta = F("sent_at") - F("created_at")
        aggregates = {
            f"le_{b}": Count("id", filter=Q(delta__lte=timedelta(seconds=b)))
            for b in DELIVERY_BUCKETS
        }
        rows = (
            Notification.objects.filter(status=Notification.Status.SENT, sent_at__isnull=False)
            .annotate(delta=delta)
            .values("channel")
            .annotate(total=Count("id"), seconds=Sum("delta"), **aggregates)
            .order_by("channel")
        )
        for typed_row in rows:
            row: dict[str, Any] = dict(typed_row)  # the bucket columns are dynamic
            buckets = [(str(float(b)), row[f"le_{b}"]) for b in DELIVERY_BUCKETS]
            buckets.append(("+Inf", row["total"]))
            histogram.add_metric(
                [row["channel"]], buckets, row["seconds"].total_seconds() if row["seconds"] else 0
            )
        return histogram

    def _celery(self, now) -> Iterator[Metric]:
        depth = GaugeMetricFamily("pulse_celery_queue_depth", "Messages waiting", labels=["queue"])
        depths = _queue_depths()
        for queue, n in (depths or {}).items():
            depth.add_metric([queue], n)
        yield depth
        yield GaugeMetricFamily(
            "pulse_celery_broker_up", "1 if the broker answered", value=1 if depths else 0
        )
        workers = _worker_count()
        if workers is not None:
            yield GaugeMetricFamily(
                "pulse_celery_workers", "Celery workers answering a ping", value=workers
            )
        last = heartbeat.last_run()
        if last is not None:
            yield GaugeMetricFamily(
                "pulse_beat_last_run_timestamp_seconds",
                "Unix time of the last Beat heartbeat",
                value=last,
            )


def build_registry() -> CollectorRegistry:
    registry = CollectorRegistry()
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        multiprocess.MultiProcessCollector(registry)
    else:

        class _Process:
            def collect(self):
                return REGISTRY.collect()

        registry.register(_Process())
    registry.register(StateCollector())
    return registry


def metrics_view(request: HttpRequest) -> HttpResponse:
    import hmac

    from django.http import Http404

    token = settings.METRICS_TOKEN
    if not token:
        raise Http404  # disabled, and indistinguishable from "no such route"
    header = request.headers.get("Authorization", "")
    supplied = header.removeprefix("Bearer ") if header.startswith("Bearer ") else ""
    if not hmac.compare_digest(supplied.encode(), token.encode()):
        return HttpResponse("unauthorized", status=401, headers={"WWW-Authenticate": "Bearer"})
    body = generate_latest(build_registry())
    return HttpResponse(body, content_type=CONTENT_TYPE_LATEST)


_ROUTE_PARAM = re.compile(r"\(\?P<(\w+)>[^)]*\)")


def route_template(request: HttpRequest) -> str:
    """`api/v1/services/{pk}/`: a bounded label (never the raw path, which has ids in it)."""
    match = getattr(request, "resolver_match", None)
    if not match or not match.route:
        return "unmatched"
    text = _ROUTE_PARAM.sub(r"{\1}", match.route)
    return text.replace("^", "").replace("$", "").replace("\\.", ".")


def observe_request(request: HttpRequest, status: int, seconds: float) -> None:
    route = route_template(request)
    HTTP_REQUESTS.labels(request.method, route, str(status)).inc()
    HTTP_LATENCY.labels(request.method, route).observe(seconds)
    if route == "api/v1/events/":
        INGEST_LATENCY.observe(seconds)
        if status != 202:  # the view counts accepted/ignored itself, with the outcome
            INGEST_REQUESTS.labels(f"rejected_{status}").inc()
