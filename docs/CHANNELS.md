# Notification channels

How a page reaches a person, what each channel guarantees, and what has and has not been proven.

| Channel | Needs | Verified against |
|---|---|---|
| In-app inbox | nothing (always created) | real code, real DB |
| Email | `EMAIL_HOST` (Mailpit in dev) | Mailpit in the Docker drills; any SMTP server |
| SMS | Twilio (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`) + a **verified** phone | a local fake Twilio speaking HTTP. **Not a live carrier.** |
| Voice call | same as SMS | the same fake. **Not a live call.** |
| Webhook | the person's own https URL (Slack incoming webhook, Teams workflow, anything) | a local fake receiver |
| Browser push | not built | n/a |

## Personal notification rules

`/api/v1/me/notification-rules/`: ordered steps of the form "after N minutes (0-1440), if still
unanswered, use channel X", optionally only for high- or low-urgency incidents.

- **No enabled rules: the default.** Inbox + email, immediately (the behaviour before rules existed).
- **With rules:** the inbox entry is still always created; the rules matching the incident's urgency are
  the rest of the plan. Someone who wants "SMS now, call after 5 minutes" gets exactly that and no email.
- **Snapshotted per page.** When a page happens, each step becomes a `Notification` row carrying its
  `rule_snapshot`, its `destination` (phone number, or webhook *host*), and for a later step a
  `not_before` time. Editing or deleting rules afterwards never changes a page already made, and
  re-running the same page (a retried task) does not re-read the rules (`page_key`).
- **The database is the timer.** A later step is `pending` with `not_before`; the delivery task is
  scheduled for that time, and if its message is lost the 60 s stuck sweep re-drives it once due.
  It is never sent early (I19).
- **Answered pages stop.** Acknowledging (by anyone) cancels everyone's later steps for that incident,
  and the claim guard cancels any it missed (I18). Resolving cancels everything pending (C1).
  Maintenance incidents page nobody (I13); debug mode records every step as a dry run (I12).
- **Unreachable is loud, not silent.** A step whose channel cannot work (SMS not configured, phone not
  verified, no webhook) is created as `failed` with a `notification_failed` timeline event *when the
  page happens*, not discovered after the delay. The API refuses to create such a rule in the first
  place, and changing or clearing a phone number or webhook disables the rules that needed it.

## SMS and voice (Twilio)

- **Phone verification:** `PATCH /me/contact/ {phone_number}` (E.164), then `POST
  /me/contact/phone/send-code/` (6 digits, valid 10 minutes, 5 sends per hour per user) and `POST
  /me/contact/phone/verify/ {code}`. Only a keyed hash of the code is stored; 5 wrong guesses and even
  the right code is refused until a new one is sent. A changed number is unverified again.
- **Only the verified number is ever used.** At send time the step's frozen number must still be the
  person's verified number, or the step fails permanently: a page never goes to a number its owner
  has since removed.
- **SMS is one GSM-7 segment (≤160 characters).** Text is folded to printable ASCII (accents folded,
  emoji and GSM extension characters dropped), the title is truncated, and the acknowledge link is
  never cut. A property test checks this for arbitrary Unicode titles.
- **Voice** speaks the incident and gathers one key: `1` acknowledges, via the same single-use
  capability as the link (`/api/v1/webhooks/twilio/voice/<token>/`).
- **Delivery receipts** (`/api/v1/webhooks/twilio/status/`) and keypresses are accepted only with a
  valid `X-Twilio-Signature` (HMAC-SHA1 of the exact public URL and form fields, constant-time
  compare); without `TWILIO_AUTH_TOKEN` both endpoints answer 404. Receipts are idempotent and
  monotonic: replays and out-of-order callbacks never move a row backwards; a carrier failure is
  recorded on the timeline once. `PUBLIC_BASE_URL` must be the origin Twilio calls, because the
  signature covers that URL.
- **Failure classification:** Twilio 4xx (bad number, unverified trial number) fails the step at once;
  5xx, 429 and network errors are retried with backoff up to 5 attempts.

## Webhooks

`PATCH /me/contact/ {webhook_url}` stores the URL (often itself a secret: it is never returned, only
its host) and returns a signing secret **once** (`POST /me/contact/webhook/rotate-secret/` makes a new
one). Each delivery is a JSON POST with a Slack/Teams-compatible `text` plus structured fields and
acknowledge/resolve links, and headers:

```
X-Pulse-Timestamp: 1767787200
X-Pulse-Signature: v1=<hex HMAC-SHA256(secret, "<timestamp>.<raw body>")>
X-Pulse-Delivery:  <idempotency key>    (deduplicate on this)
```

Receivers should recompute the signature over the raw body and reject timestamps older than a few
minutes. **SSRF guard** (`core/safe_http.py`): https and port 443 only, no credentials in the URL,
every resolved address must be public (loopback, private, link-local and the cloud metadata address,
CGNAT, multicast, reserved and IPv4-mapped forms refused), the socket connects to the address that was
checked (no DNS rebinding), TLS is verified against the hostname, redirects are never followed, the
response body is capped. Checked when the URL is saved and again on every send. 2xx is success; 408,
429 and 5xx retry; any other status (including redirects) fails permanently.

## One-tap acknowledge/resolve links

Email, SMS and webhook pages carry `https://<PUBLIC_BASE_URL>/a/<token>/`. The token is 16 random
bytes, an expiry, the action and a 96-bit HMAC (key derived from `SECRET_KEY` with a purpose label);
the `ActionLink` row is the authority. Links expire (`ACTION_LINK_TTL_HOURS`, default 12) and work
**once** (an atomic `UPDATE … WHERE used_at IS NULL`; two simultaneous clicks act once, tested with six
threads). Opening a link only shows a confirmation; only the POST from that page acts, so mail scanners
and link previewers cannot acknowledge anything. A link stops working if its owner is deactivated or
leaves the team, and an action that is refused (already acknowledged) does not spend it. Every invalid,
forged, expired or used link gets the same 404 page; the endpoint is rate limited (30/min per client).

## What is not verified

- **No real SMS was sent and no real call was placed.** The Twilio integration was exercised against a
  local HTTP fake that checks the request shape, auth and form fields, and against Twilio's documented
  signature algorithm. A live account test (and trial-account restrictions on unverified numbers) is
  left to whoever deploys it.
- **Slack/Teams rendering** of the payload was not checked against the live services.
- Delivery is at-least-once per attempt, as for email: a worker that dies after Twilio accepted a
  message but before recording it can cause a duplicate SMS on retry. Twilio has no idempotency key
  for messages.
- The simulator replaces the external channels' `send` with a recorder, so it proves timing,
  cancellation and duplication properties of the pipeline, not the channel code itself (which the
  channel tests above cover).
