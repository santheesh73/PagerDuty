# Observability

How to tell that Pulse is doing its one job (paging a human on time), and how to be told when it
is not. Everything here is **off by default** and configured through environment variables.

| Signal | Where | Turn on with |
|---|---|---|
| Errors (backend + browser) | Sentry | `SENTRY_DSN`, `VITE_SENTRY_DSN` |
| Metrics | `GET /metrics` (Prometheus) | `METRICS_TOKEN` |
| Alert rules + dashboard | `ops/alerts.yml`, `ops/grafana/pulse.json` | `docker-compose.observability.yml` |
| Dead-man's switch | external monitor pinged by Beat | `HEARTBEAT_URL` |
| Self-check | `manage.py selfcheck` | always available |
| Logs | JSON on stdout, one request id from HTTP to Celery | always on |

## Metrics

`/metrics` answers **404 until `METRICS_TOKEN` is set**, then requires `Authorization: Bearer <token>`
(constant-time compare, 401 otherwise). The bundled nginx does not proxy it, so it is only reachable
on the internal network; give Prometheus the token as a file (see `ops/prometheus.yml`).

State metrics are computed from Postgres/Redis **at scrape time**, so they are right across every
gunicorn worker and restart. Request metrics are counted in-process and merged across workers with
`prometheus_client` multiprocess mode (`PROMETHEUS_MULTIPROC_DIR`, set by the container entrypoint).

| Metric | Type | Meaning |
|---|---|---|
| `pulse_incidents_open{severity}` | gauge | open incidents. `severity` is the incident urgency (`high`/`low`), which is derived from alert severity at open |
| `pulse_incidents_triggered_total`, `pulse_incidents_resolved_total` | counter | rows in the database (a retention purge resets them; `rate()` copes) |
| `pulse_escalation_sweeper_lag_seconds` | gauge | age of the most overdue escalation timer, 0 when none is due. Healthy is < ~35 s |
| `pulse_escalations_overdue` | gauge | triggered incidents whose timer has expired |
| `pulse_notifications_total{channel,status}` | counter | terminal outcomes only (`sent`, `failed`, `dry_run`, `cancelled`). `pending` is a gauge because it goes down |
| `pulse_notifications_pending`, `pulse_notifications_stuck` | gauge | pending pages; pending for > 5 minutes (redelivery is failing) |
| `pulse_notification_delivery_seconds{channel}` | histogram | created to sent, over all sent notifications |
| `pulse_ingest_requests_total{result}` | counter | `accepted`, `ignored`, or `rejected_<http status>` |
| `pulse_ingest_latency_seconds` | histogram | Events API latency |
| `pulse_http_requests_total{method,route,status}`, `pulse_http_request_duration_seconds{method,route}` | counter, histogram | `route` is the URL *template* (`api/v1/incidents/{pk}/`), never the raw path |
| `pulse_celery_queue_depth{queue}`, `pulse_celery_broker_up` | gauge | Redis list length per queue; whether the broker answered |
| `pulse_celery_workers` | gauge | workers answering a ping (cached 30 s: `ping` blocks about a second) |
| `pulse_beat_last_run_timestamp_seconds` | gauge | Unix time of Beat's last heartbeat |

Cost: a scrape runs about ten small aggregate queries. At the intended scale (thousands of
incidents) that is milliseconds; the delivery histogram scans sent notifications, which a
[retention policy](DATA_SAFETY.md#retention) keeps bounded.

## Alerts

`ops/alerts.yml` has 14 rules. The important ones are about Pulse failing to page:

| Alert | Fires when | First thing to do |
|---|---|---|
| `PulseBeatStalled` | no Beat heartbeat for over 3 minutes (fires about 3.5 minutes after Beat dies); `PulseBeatNeverSeen` covers a wiped Redis with Beat also down, after 3 minutes | <a id="beat-stalled"></a>`docker compose ps beat`; exactly one must run. Restart it; the 30 s sweeper catches up on everything overdue |
| `PulseNoWorkers` | no worker answers a ping | <a id="no-workers"></a>`docker compose logs worker-escalations worker`; check Redis |
| `PulseEscalationSweeperLag` | an escalation timer overdue > 2 minutes | <a id="sweeper-lag"></a>Beat or the escalations worker is down or wedged; `manage.py selfcheck` says which |
| `PulseNotificationsStuck` | a page pending > 5 minutes | <a id="stuck-notifications"></a>Worker/SMTP problem; `last_error` on the notification; the 60 s stuck sweep re-drives |
| `PulseIngestRejectingServerErrors` | Events API returns 5xx | <a id="ingest-errors"></a>Alerts are being dropped. Database down? `/readyz` |

`backend/apps/core/tests/test_ops_rules.py` fails if any rule or dashboard panel names a metric that
`/metrics` does not expose, so a rename cannot orphan an alert. CI also runs `promtool check rules`.

Run it locally:

```bash
export SECRET_KEY=$(openssl rand -hex 32) METRICS_TOKEN=$(openssl rand -hex 24) GRAFANA_PASSWORD=change-me
docker compose -f docker-compose.prod.yml -f docker-compose.observability.yml up -d
# Prometheus http://localhost:9090   Grafana http://localhost:3000 (dashboard "Pulse — paging path")
```

## Dead-man's switch

In-stack alerts cannot report that the stack (or Prometheus, or the host) is gone. So Beat runs a
task every minute that stamps `pulse_beat_last_run_timestamp_seconds` and, **only while the sweeper
and delivery checks pass**, does `GET $HEARTBEAT_URL`. Point it at healthchecks.io, Cronitor,
Better Stack, etc. and let *that* service alert on silence. Silence therefore means any of: Beat, the
broker, the worker, the database, the sweeper or the host is broken.

`manage.py selfcheck` runs the same checks and exits non-zero on failure (`--ping` also hits the URL).
A host cron entry makes a second, Celery-independent switch:

```cron
* * * * *  docker compose -f /srv/pulse/docker-compose.prod.yml exec -T api python manage.py selfcheck --no-beat --ping
```

## Sentry

Both SDKs initialise **only** when a DSN is set. Scrubbing is deliberate because Pulse handles
passwords, session cookies and integration keys:

- backend: `send_default_pii=False`, no local variables, no request bodies, cookies, query strings or
  auth headers, and `before_send` redacts any key that looks like a secret anywhere in the event;
- frontend: `dataCollection` set to collect nothing, plus the same `beforeSend` scrubber; the SDK is a
  separate chunk that is not even built into the bundle unless `VITE_SENTRY_DSN` was set;
- `release` is the git SHA (`SENTRY_RELEASE`/`GIT_SHA` for the API, `VITE_RELEASE` for the SPA).

## Logs

JSON on stdout for the API **and** the Celery workers (`worker_hijack_root_logger=False` keeps Django's
handler). Every line carries `request_id`: it is read from `X-Request-ID` (or generated), attached to
the Celery message headers, and restored in the worker, so `grep <id>` reconstructs one alert's path.
Each HTTP request logs one `pulse.access` line: method, route template, status, duration, user id.

What is never logged, enforced by tests: request bodies, query strings, headers, passwords,
session ids, integration keys. (`django.request` records carry the request object, whose repr includes
the query string, so a filter strips it.) The gunicorn access log is disabled for the same reason.

## What this does not claim

- Sentry was exercised with a fake transport path only (scrubber unit tests), **not against a live
  Sentry project**.
- `promtool` and Grafana loading are verified by CI / by hand on a Docker host; the dashboard JSON was
  not rendered in this sandbox.
- A scrape of `pulse_celery_workers` blocks up to 1 s when the broker is down (then cached for 30 s).
