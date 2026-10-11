# API conventions

The machine-readable contract is the OpenAPI 3 schema: [`backend/openapi.yaml`](../backend/openapi.yaml), served at `/api/schema/` with Swagger UI at `/api/docs/`. CI regenerates it and fails if the committed copy differs. This page covers what a schema can't say: versioning, errors, pagination, retries and limits. Each rule below names the test that pins it.

## Versioning

- Everything lives under **`/api/v1/`**. The only unversioned paths are `/api/schema/`, `/api/docs/`, the health probes (`/healthz`, `/readyz`), `/metrics` and the signed action links (`/a/…`).
- **Within v1, changes are additive only**: new endpoints, new response fields, new optional parameters. Clients must ignore response fields they don't know.
- A breaking change (removing or renaming a field, tightening validation of an existing field, changing a status code) would ship as `/api/v2/`, served next to v1 for at least one release, with the change listed in the release notes. None has been needed yet, so no deprecation headers exist.
- The Events API (`POST /api/v1/events/`) is the integration contract that monitoring systems are configured against, so it changes least of all.

## Authentication

- **Browser API**: Django session cookie plus CSRF. Unsafe methods (POST, PUT, PATCH, DELETE) need the `X-CSRFToken` header; `GET /api/v1/auth/csrf/` sets the cookie. Sign-in is `POST /api/v1/auth/login/`, followed by `POST /api/v1/auth/mfa/` when two-factor authentication is on.
- **Events API**: authenticated only by `routing_key` in the body (a service's integration key). It uses no session and no CSRF. An unknown key is `403 invalid_routing_key`.
- **Twilio callbacks** (`/api/v1/webhooks/twilio/…`): verified by Twilio's `X-Twilio-Signature`.

## Errors

Every error under `/api/`, including 404s for unknown paths, 413s and unhandled 500s, uses one envelope:

```json
{"error": {"code": "validation_error", "message": "Request validation failed.", "details": {"name": ["This field may not be blank."]}}}
```

Branch on `code`, not on `message`; messages are written for people and may change. `details` is an object; for validation errors it maps field names to messages.

| Status | `code` | When |
|---|---|---|
| 400 | `parse_error` | The body is not valid JSON |
| 400 | `invalid_idempotency_key` | `Idempotency-Key` has characters outside `A–Z a–z 0–9 _ . : -` or is over 255 long |
| 401 / 403 | `not_authenticated`, `authentication_failed` | No valid session. The SPA treats this mid-session as "your session has ended" |
| 403 | `permission_denied` | Signed in, but your role on that team does not allow it |
| 403 | `mfa_enrollment_required` | Your account must set up two-factor authentication before doing anything else |
| 403 | `invalid_routing_key` | Events API: no service has that integration key |
| 404 | `not_found` | No such object **or no access to it**: outsiders get 404, never 403, so ids can't be probed. Also unknown paths, and a bad `page` or `cursor` |
| 405 | `method_not_allowed` | |
| 409 | `invalid_transition` | For example, acknowledging a resolved incident |
| 409 | `conflict`, `in_use`, `ingest_conflict` | The object changed, or is still referenced (for example, deleting a policy a service uses) |
| 409 | `idempotency_in_progress` | A request with the same `Idempotency-Key` is still running |
| 409 | `idempotency_response_withheld` | A retried request already succeeded, but its response held a one-time secret, so it is not replayed |
| 413 | `payload_too_large` | The body is over 1 MiB |
| 422 | `validation_error` | A field or **query parameter** is invalid. `details` names it |
| 422 | `limit_exceeded` | Over a product limit (table below). `details` has `limit`, `max`, `actual` |
| 422 | `idempotency_key_reused` | The same `Idempotency-Key` was sent with a different body |
| 429 | `throttled` | Rate limited. Honour `Retry-After` |
| 500 | `server_error` | A bug. The message includes the request id, which is the `X-Request-ID` the logs carry |

Pinned by `backend/apps/core/tests/test_api_quality.py`: JSON 404, 500 with the request id and no internals, 400 parse error, 422 validation, 413.

## Request ids

Every response carries `X-Request-ID`. Send your own (8 to 64 characters from `A–Z a–z 0–9 _ . -`) to correlate with your logs; anything else is replaced by a generated id. The id appears in every log line for that request and in the Celery tasks it enqueues.

## Lists: pagination, ordering, filters

Two pagination styles:

- **Cursor** for the lists that grow without bound: `GET /incidents/`, `GET /incidents/{id}/timeline/` and `GET /incidents/{id}/alerts/`. The response is `{"next", "previous", "results"}`; follow `next` until it is `null`. A cursor stays correct while new rows arrive, so polling clients neither skip nor repeat rows. 25 per page (timeline: 100); `page_size` goes up to 100.
- **Page number** for everything else that pages: `{"count", "next", "previous", "results"}`. `page` starts at 1; `page_size` defaults to 25, at most 100. A `page` past the end is `404 not_found`. A `page_size` that is not a positive integer falls back to the default.
- Small, bounded collections are returned whole, as a plain array: `teams`, `users`, schedule overrides, notification rules, sessions, `oncalls`.

**Ordering is fixed per endpoint and always total**: the last sort key is the primary key, so rows that tie on name or timestamp (an alert storm opens many incidents in the same millisecond) still come back in one order on every page. `test_every_list_has_a_total_order_ending_in_a_unique_field` checks every router list. `test_cursor_pages_never_skip_or_repeat_incidents_that_share_a_timestamp` proves it with 25 incidents opened in the same instant. Before the fix it returned only 15 to 19 of them.

| Endpoint | Order |
|---|---|
| `incidents` | newest `triggered_at` first, then id |
| `incidents/{id}/timeline`, `notifications`, `audit-events`, `me/sessions` | newest first, then id |
| `incidents/{id}/alerts` | newest `received_at` first, then id |
| `services`, `escalation-policies`, `schedules`, `teams`, `users` | name, then id |
| `schedules/{id}/overrides` | `start`, then id |

**Filters** are query parameters. Every typed filter (ids, timestamps, enumerations) is validated: a malformed value (`team=abc`, `since=yesterday`, `status=triggred`) is a `422 validation_error` naming the parameter. It is never ignored and never a 500 (`test_a_bad_query_parameter_is_a_422_naming_it`).

| Endpoint | Parameters |
|---|---|
| `incidents` | `status` (comma-separated `triggered,acknowledged,resolved`), `urgency` (`high`/`low`), `service`, `team`, `assignee` (user id or `me`), `since`/`until` (ISO-8601), `search` (title text, `#number` or exact dedup key) |
| `services` | `team`, `mode` (`active`/`maintenance`/`debug`), `escalation_policy` |
| `escalation-policies`, `schedules` | `team` |
| `users` | `team` |
| `notifications` | `unread=true` |
| `audit-events` | `action` (e.g. `auth.login`), `team` |
| `schedules/{id}/overrides` | `since` (overrides ending after it) |
| `analytics/summary`, `analytics/timeseries` | `since`, `until` (at most 366 days apart), `service`, `team`; timeseries also `tz` (IANA zone) |

Timestamps are ISO-8601. One without an offset is read as UTC.

## Retrying writes: `Idempotency-Key`

Any `POST`, `PUT`, `PATCH` or `DELETE` under `/api/v1/` accepts an `Idempotency-Key` header (1 to 255 characters: letters, digits, `_ . : -`; a UUID is ideal). If you didn't see the response (timeout, dropped connection), send the identical request again with the same key:

- **The first attempt finished**: you get its stored response with `Idempotent-Replayed: true`. Nothing runs twice.
- **The first attempt is still running**: `409 idempotency_in_progress`. Retry shortly.
- **The same key with a different body**: `422 idempotency_key_reused`.
- **The response held a one-time secret** (a new integration key, an MFA secret, backup codes, a webhook signing secret): those responses are `Cache-Control: no-store`, so only a tombstone is kept and the retry gets `409 idempotency_response_withheld`. The secret never reaches Redis (`apps/security/tests/test_secret_responses.py`).

Keys are scoped to the caller: your user, or for the Events API the routing key. Two callers using the same key never see each other's responses. Keys are remembered for 24 hours. 5xx responses are not stored, so a retry after a server error runs again.

This is a convenience for clients, not what keeps paging correct. Redis is disposable, so if it is down the header is ignored and the request runs normally. The guarantees that matter live in Postgres: one open incident per dedup key, one notification per page key. The Events API is idempotent per `dedup_key` without this header.

## Size and product limits

- Request bodies: **1 MiB** for any `/api/` request (`413 payload_too_large`, checked before any view or throttle reads the body). nginx enforces the same limit in front.
- Events API payload: **512 KiB** (`422 limit_exceeded`).

| Limit | Value |
|---|---|
| Escalation levels per policy | 10 |
| Targets per level | 5 |
| Layers per schedule | 5 |
| Members per layer | 50 |
| Note length | 5,000 characters |
| Personal notification rules | 10 |
| Maintenance or debug window | 24 hours |

The source of truth is `backend/apps/core/limits.py`.

## Rate limits

Limits live in Redis and **fail open**: if Redis is down, requests are let through and a warning is logged. Dropping alerts because the limiter is down would be worse than briefly not limiting. Only a cache error lets a request through; anything else surfaces (`test_throttles_fail_open_only_when_the_cache_is_down`). Over the limit, the response is `429 throttled` with `Retry-After`.

| What | Default | Keyed by | Setting |
|---|---|---|---|
| Events API | 120/min | integration key (hashed) | `THROTTLE_EVENTS` |
| Sign-in | 10/min | client address | `THROTTLE_LOGIN` |
| Sign-in, per account | locked for 15 min after 10 failures | account | `LOGIN_LOCKOUT_FAILURES`, `LOGIN_LOCKOUT_SECONDS` |
| Two-factor code at sign-in, MFA and password changes | 10/min | client address / user | `THROTTLE_MFA` |
| Password reset requests | 10/hour | client address | `THROTTLE_PASSWORD_RESET` |
| Phone verification codes (each is a paid SMS) | 5/hour | user | `THROTTLE_PHONE_CODE` |
| Signed action links (`/a/…`) | 30/min | client address | fixed |

Client addresses come from `X-Forwarded-For` only as far as `NUM_PROXIES` trusted proxies allow, so a client can't choose its own bucket.

## CORS

None by default: the SPA is served from the same origin as the API. `CORS_ALLOWED_ORIGINS` opens it to named origins, and `Idempotency-Key` is an allowed request header.
