#!/usr/bin/env python3
"""Mutation spot-check: does the test suite notice when a guarantee is removed?

Each mutation edits one critical line (a scoping filter, a lock, the dedup index...), runs the
tests that are supposed to protect it, and reports CAUGHT or SURVIVED. A survivor is either a real
gap in the tests or an *equivalent* mutant (a change that cannot alter behaviour), and must be
explained. The file is restored after every mutation.

    python3 scripts/mutate.py --list
    python3 scripts/mutate.py                      # everything
    python3 scripts/mutate.py --only scope-services,skip-locked
    python3 scripts/mutate.py --full               # run the whole suite for survivors too

Isolation: set DATABASE_URL (its own database) and REDIS_URL so this never touches a dev stack.
It edits files in the working tree and restores them; run it on a clean checkout.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
ID = "(lambda q, *_: q)"  # identity: swallows scope_to_teams(queryset, user)


@dataclass
class M:
    name: str
    file: str
    old: str
    new: str
    tests: list[str]
    why: str = ""
    create_db: bool = False
    equivalent: str = ""  # set when a survivor is expected to be an equivalent mutant
    extra: dict = field(default_factory=dict)


MATRIX = ["apps/core/tests/test_tenant_matrix.py"]
SAFE = ["apps/core/tests/test_data_safety.py"]
CHAN = ["apps/notifications/tests"]
SEC = ["apps/security/tests"]
OBS = ["apps/core/tests/test_observability.py"]
API = "apps/core/tests/test_api_quality.py"
DEMO = "apps/core/tests/test_demo_mode.py"

MUTATIONS: list[M] = [
    # --- tenancy: team scoping on every list endpoint ---------------------------------------
    M("scope-services", "apps/catalog/views.py",
      'return scope_to_teams(\n            Service.objects.select_related("escalation_policy")',
      f'return {ID}(\n            Service.objects.select_related("escalation_policy")', MATRIX,
      "services list not scoped to the caller's teams"),
    M("scope-policies", "apps/escalations/views.py",
      "return scope_to_teams(policies_with_rules(), self.request.user)",
      f"return {ID}(policies_with_rules(), self.request.user)", MATRIX, "policies list unscoped"),
    M("scope-oncalls", "apps/escalations/views.py",
      "policies = scope_to_teams(EscalationPolicy.objects.all(), request.user)",
      f"policies = {ID}(EscalationPolicy.objects.all(), request.user)", MATRIX,
      "on-call overview unscoped"),
    M("scope-schedules", "apps/schedules/views.py",
      "return scope_to_teams(schedules_with_layers(), self.request.user)",
      f"return {ID}(schedules_with_layers(), self.request.user)", MATRIX, "schedules unscoped"),
    M("scope-overrides", "apps/schedules/views.py",
      "schedules = scope_to_teams(Schedule.objects.all(), self.request.user)",
      f"schedules = {ID}(Schedule.objects.all(), self.request.user)", MATRIX,
      "overrides readable across teams"),
    M("scope-incidents", "apps/incidents/selectors.py",
      "return incidents.filter(service__team_id__in=member_team_ids(user))",
      "return incidents", MATRIX, "incidents (list, detail, actions, timeline, alerts) unscoped"),
    M("scope-analytics", "apps/analytics/selectors.py",
      "incidents = incidents.filter(service__team_id__in=member_team_ids(user))",
      "pass", MATRIX, "analytics count other teams' incidents"),
    M("scope-teams", "apps/accounts/views.py",
      "return teams.filter(pk__in=member_team_ids(self.request.user))", "return teams", MATRIX,
      "team list unscoped"),
    M("scope-users", "apps/accounts/views.py",
      "users = User.objects.filter(is_active=True, memberships__team_id__in=teams)",
      "users = User.objects.filter(is_active=True)", MATRIX, "user list unscoped"),
    M("scope-notifications", "apps/notifications/views.py",
      "user=actor(self.request), channel=Notification.Channel.IN_APP",
      "channel=Notification.Channel.IN_APP", MATRIX, "inbox shows other users' notifications"),
    # --- paging correctness -----------------------------------------------------------------
    M("skip-locked", "apps/escalations/engine.py", "select_for_update(skip_locked=True, no_key=True, of=",
      "select_for_update(no_key=True, of=", ["apps/escalations/tests/test_engine.py"],
      "blocking lock instead of skip-locked",
      equivalent="A blocking lock re-checks the guarded filter once it acquires the row, so "
      "behaviour is the same; skip_locked is a latency optimisation (callers never wait)."),
    M("dedup-index", "apps/incidents/migrations/0001_initial.py",
      'condition=models.Q(("status", "resolved"), _negated=True),',
      'condition=models.Q(("status", "never-a-status")),',
      ["apps/incidents/tests/test_dedup_constraint.py", "apps/alerting/tests/test_ingest.py"],
      "partial unique index no longer enforces dedup", create_db=True),
    M("idempotency-key", "apps/notifications/actions.py",
      'key = f"incident:{incident_id}:level:{level}:loop:{loop}:user:{user_id}:channel:{channel}"',
      'key = f"incident:{incident_id}:level:{level}:loop:{loop}:channel:{channel}"',
      ["apps/notifications/tests", "apps/escalations/tests/test_engine.py"],
      "pages for different users collide on one key"),
    M("on-commit", "apps/core/dispatch.py", "    transaction.on_commit(_send)", "    _send()",
      ["apps/core/tests/test_dispatch_order.py"], "tasks enqueued before commit"),
    M("inactive-users", "apps/escalations/engine.py",
      "users = User.objects.filter(is_active=True).in_bulk(ordered)",
      "users = User.objects.all().in_bulk(ordered)",
      ["apps/escalations/tests/test_inactive_responders.py"], "deactivated users get paged"),
    M("first-response-guard", "apps/incidents/actions.py",
      "        and incident.first_response_at is None\n", "        and True\n",
      ["apps/incidents/tests", "apps/analytics/tests"], "first_response_at can be overwritten"),
    M("incident-row-lock", "apps/incidents/actions.py",
      "Incident.objects.select_for_update(no_key=True, of=(\"self\",))\n        .select_related(\"service\")",
      "Incident.objects\n        .select_related(\"service\")",
      ["apps/incidents/tests/test_locking.py"], "incident actions no longer serialise"),
    M("ingest-advisory-lock", "apps/alerting/actions.py",
      'advisory_xact_lock("incident-key", service.pk, incident_key)', "pass",
      ["apps/alerting/tests/test_ingest_churn.py"], "open-or-attach no longer serialised per key"),
    M("ingest-row-lock", "apps/alerting/actions.py",
      "Incident.objects.select_for_update(no_key=True, of=(\"self\",))\n                    .filter(service=service",
      "Incident.objects\n                    .filter(service=service",
      ["apps/incidents/tests/test_locking.py"], "attach can overtake a resolve"),
    M("deliver-claim-lock", "apps/notifications/actions.py",
      "        notification = (\n            Notification.objects.select_for_update(of=(\"self\",))\n"
      "            .select_related(\"incident__service\", \"user\")",
      "        notification = (\n            Notification.objects\n"
      "            .select_related(\"incident__service\", \"user\")",
      ["apps/notifications/tests/test_delivery_claim.py", "apps/core/tests/test_audit_gaps.py"],
      "two workers can claim one page"),
    M("snapshot-guard", "apps/escalations/guards.py",
      "    incidents = list(open_incidents_naming(kind, instance.pk)[:5])",
      "    incidents = []", ["apps/escalations/tests/test_snapshot_references.py"],
      "schedules/users named by open incidents can be deleted"),
    M("resolved-guard", "apps/notifications/actions.py",
      "        if incident.status == Status.RESOLVED:", "        if False:",
      ["apps/notifications/tests/test_delivery.py"], "a page is sent after the incident resolved"),
    M("maintenance-guard", "apps/notifications/actions.py",
      "    if incident.is_maintenance:\n        return []", "    if False:\n        return []",
      ["apps/alerting/tests/test_ingest.py"], "maintenance incidents can page"),
    # --- observability ----------------------------------------------------------------------
    M("metrics-auth", "apps/core/metrics.py",
      "    if not hmac.compare_digest(supplied.encode(), token.encode()):", "    if False:",
      OBS, "/metrics readable without the token"),
    M("metrics-disabled-by-default", "apps/core/metrics.py", "    if not token:\n        raise Http404",
      "    if False:\n        raise Http404", OBS, "/metrics open when no token is configured"),
    M("sweeper-lag-filter", "apps/core/selfcheck.py",
      "        status=Status.TRIGGERED, next_escalation_at__lte=now\n    ).aggregate",
      "        next_escalation_at__lte=now\n    ).aggregate", OBS,
      "sweeper-lag gauge counts incidents that no longer escalate"),
    M("heartbeat-health-gate", "apps/core/tasks.py",
      "    if all(c.ok for c in selfcheck.run(include_beat=False)):", "    if True:", OBS,
      "dead-man's switch pings even while the sweeper is stalled"),
    M("sentry-secret-keys", "apps/core/sentry.py", 'r"pass|secret|token|', 'r"secret|token|', OBS,
      "Sentry events keep password fields"),
    M("log-request-redaction", "apps/core/logging.py", "            record.request = None",
      "            record.request = record.request", OBS,
      "django.request log records keep the query string"),
    # --- data safety -----------------------------------------------------------------------
    M("migrate-lock", "apps/core/management/commands/migrate_safely.py",
      "                if cursor.fetchone()[0]:", "                if True:", SAFE,
      "concurrent migrate on a fresh database crashes (3 of 4 processes)"),
    M("retention-keeps-open", "apps/core/retention.py",
      "Incident.objects.filter(status=Status.RESOLVED, resolved_at__lt=cutoff)",
      "Incident.objects.filter(triggered_at__lt=cutoff)", SAFE,
      "retention deletes open incidents"),
    M("retention-off-by-default", "apps/core/retention.py", "    if days <= 0:", "    if False:", SAFE,
      "RETENTION_DAYS=0 deletes everything"),
    M("retention-alerts", "apps/core/retention.py",
      "        alerts += Alert.objects.filter(incident_id__in=ids).delete()[0]\n", "", SAFE,
      "alert payloads survive the purge of their incident"),
    M("db-statement-timeout", "config/settings/base.py", '("statement_timeout", "DB_STATEMENT_TIMEOUT_MS", 15_000),',
      '("statement_timeout", "DB_STATEMENT_TIMEOUT_MS", 0),', SAFE,
      "a runaway query is no longer cancelled"),
    # --- channels -------------------------------------------------------------------------
    M("step-not-before", "apps/notifications/actions.py",
      "            if now < notification.not_before:", "            if False:", CHAN,
      "a delayed step is sent early"),
    M("step-cancel-on-ack", "apps/notifications/actions.py",
      "            if incident.status != Status.TRIGGERED:\n                # I18",
      "            if False:\n                # I18", ["apps/notifications/tests/test_rules.py"],
      "a delayed step is sent after the incident was acknowledged (claim guard)"),
    M("page-snapshot-once", "apps/notifications/actions.py",
      "        if Notification.objects.filter(incident=incident, page_key=key_prefix).exists():",
      "        if False:", CHAN, "editing rules re-plans a page that already happened"),
    M("link-single-use", "apps/notifications/links.py",
      "            jti=parsed.jti, action=parsed.action, used_at__isnull=True, expires_at__gt=now",
      "            jti=parsed.jti, action=parsed.action, expires_at__gt=now", CHAN,
      "an acknowledge link works more than once"),
    M("link-expiry", "apps/notifications/links.py",
      "    if link is None or link.used_at is not None or link.expires_at <= now:",
      "    if link is None or link.used_at is not None:", CHAN, "an expired link still opens"),
    M("link-signature", "apps/notifications/links.py",
      "    if code not in _CODE_ACTION or not hmac.compare_digest(mac, _mac(jti, expiry, code)):",
      "    if code not in _CODE_ACTION:", CHAN, "forged link tokens are accepted"),
    M("link-actor-check", "apps/notifications/link_actions.py",
      "    if not user.is_active or not has_role(user, incident.service.team_id, Role.RESPONDER):",
      "    if False:", CHAN, "a deactivated or removed person can still act via an old link"),
    M("twilio-signature", "apps/notifications/providers.py",
      "    return hmac.compare_digest(expected.encode(), signature.encode())", "    return True",
      CHAN, "unsigned Twilio callbacks are trusted"),
    M("receipt-monotonic", "apps/notifications/actions.py",
      "        if rank <= current:\n            return notification",
      "        if False:\n            return notification", CHAN,
      "replayed or late receipts move the state backwards"),
    M("ssrf-private", "apps/core/safe_http.py",
      "        if not allow_private and not _is_public(address):",
      "        if False:", ["apps/core/tests/test_safe_http.py", "apps/notifications/tests"],
      "webhooks can reach internal addresses"),
    M("ssrf-pinned-ip", "apps/core/safe_http.py",
      "        sock = socket.create_connection((self._ip, self.port), self.timeout)",
      "        sock = socket.create_connection((self.host, self.port), self.timeout)",
      ["apps/core/tests/test_safe_http.py"], "DNS rebinding: the connection re-resolves the name"),
    M("phone-code-attempts", "apps/notifications/views.py",
      "            if contact.phone_code_attempts >= CODE_MAX_ATTEMPTS:",
      "            if False:", CHAN, "unlimited guesses at a 6-digit verification code"),
    # --- security ---------------------------------------------------------------------------
    M("mfa-login-gate", "apps/accounts/views.py", "        if mfa.enabled(user):", "        if False:", SEC,
      "a password alone signs in to an MFA account"),
    M("totp-replay", "apps/security/totp.py",
      "        if step > last_step and hmac.compare_digest(hotp(key, step), code):",
      "        if hmac.compare_digest(hotp(key, step), code):", SEC, "a TOTP code can be replayed"),
    M("backup-code-single-use", "apps/security/mfa.py",
      "user=user, code_hash=_code_hash(user.pk, code), used_at__isnull=True",
      "user=user, code_hash=_code_hash(user.pk, code)", SEC, "a backup code works more than once"),
    M("mfa-attempt-limit", "apps/security/views.py",
      '            if pending["tries"] >= PENDING_ATTEMPTS:', "            if False:", SEC,
      "unlimited guesses at the second factor"),
    M("mfa-enrolment-gate", "apps/security/middleware.py",
      "            if mfa.required(user) and not mfa.enabled(user):", "            if False:", SEC,
      "admins can work without enrolling MFA"),
    M("login-lockout", "apps/accounts/views.py",
      "        return failures >= settings.LOGIN_LOCKOUT_FAILURES",
      "        return False", SEC, "no per-account lockout"),
    M("mfa-account-lockout", "apps/security/views.py",
      "        return ratelimit.count(_code_failures_key(user)) >= settings.MFA_LOCKOUT_FAILURES",
      "        return False", SEC, "second-factor guesses are only capped per password step"),
    M("throttle-skips-signed-in", "apps/core/throttling.py",
      "str | None:\n        return self.cache_format",
      "str | None:\n        if request.user.is_authenticated:\n            return None\n"
      "        return self.cache_format", SEC,
      "sign-in and code limits ignore callers who already hold a session"),
    M("prod-requires-num-proxies", "config/settings/prod.py",
      '"DATABASE_URL", "NUM_PROXIES"):', '"DATABASE_URL"):', ["apps/core/tests/test_prod_settings.py"],
      "production boots with a spoofable X-Forwarded-For"),
    M("demo-session-lock", "apps/core/demo.py",
      "(request.path in LOCKED_PATHS or request.path.startswith(LOCKED_PREFIXES))",
      "(request.path in LOCKED_PATHS)", [DEMO], "a demo visitor can end other visitors' sessions"),
    M("demo-hides-addresses", "apps/core/demo.py",
      "    return bool(settings.DEMO_ACCOUNT_GUARD) and is_demo_account(user)",
      "    return False", [DEMO], "demo visitors see each other's IP address and browser"),
    M("prod-docs-off", "config/settings/prod.py",
      'API_DOCS = env_bool("API_DOCS", False)', 'API_DOCS = env_bool("API_DOCS", True)',
      ["apps/core/tests/test_prod_settings.py"], "Swagger UI on in production by default"),
    M("swagger-unpinned", "config/settings/base.py",
      "swagger-ui-dist@5.17.14", "swagger-ui-dist@latest", ["apps/core/tests/test_api_docs.py"],
      "unpinned third-party script on the session origin"),
    M("backup-prune-empty-dir", "../scripts/backup.sh",
      '{ ls -1t "$dir"/pulse-*.dump 2>/dev/null || true; } |',
      'ls -1t "$dir"/pulse-*.dump 2>/dev/null |', ["apps/core/tests/test_backup_scripts.py"],
      "a backup on any day but the weekly one exits 2 before upload and heartbeat"),
    M("broker-socket-timeout", "config/settings/base.py",
      '"socket_timeout": 5,', '"socket_timeout": 0,', ["apps/core/tests/test_broker_settings.py"],
      "a hung broker blocks every request that enqueues"),
    M("demo-cache-cap", "config/settings/base.py",
      '"OPTIONS": {"MAX_ENTRIES": 1_000_000},', '"OPTIONS": {},',
      ["apps/core/tests/test_broker_settings.py"],
      "the demo's cache culls the reset guard and lockout counters at 300 rows"),
    M("idem-in-flight", "apps/core/idempotency.py",
      "            if not cache.add(lock_key, 1, timeout=IN_FLIGHT_TTL):", "            if False:",
      ["apps/core/tests/test_audit_gaps.py"], "a retry during the first attempt runs the write twice"),
    M("idem-events-scope", "apps/core/idempotency.py",
      '            return "rk:" + hashlib.sha256(routing_key.encode()).hexdigest()[:32]',
      '            return "rk:shared"', ["apps/core/tests/test_audit_gaps.py"],
      "one service's replayed 202 is served to another and its page is never created"),
    M("key-prefix-compare", "apps/catalog/actions.py",
      "        .filter(\n            Q(integration_key_hash=digest)",
      "        .filter(\n            Q(integration_key_prefix=key[:8])", ["apps/core/tests/test_audit_gaps.py"],
      "a key sharing only its first eight characters authenticates"),
    M("notification-key-unique", "apps/notifications/migrations/0001_initial.py",
      '("idempotency_key", models.CharField(max_length=255, unique=True)),',
      '("idempotency_key", models.CharField(max_length=255)),', ["apps/core/tests/test_audit_gaps.py"],
      "Postgres no longer enforces one row per page key", create_db=True),
    M("hsts-default-off", "config/settings/prod.py",
      'os.environ.get("SECURE_HSTS_SECONDS", str(365 * 24 * 3600))',
      'os.environ.get("SECURE_HSTS_SECONDS", "0")', ["apps/core/tests/test_audit_gaps.py"], "production sends no HSTS by default"),
    M("cookie-secure-off", "config/settings/prod.py",
      'SESSION_COOKIE_SECURE = env_bool("SECURE_COOKIES", True)',
      'SESSION_COOKIE_SECURE = env_bool("SECURE_COOKIES", False)', ["apps/core/tests/test_audit_gaps.py"],
      "the session cookie is sent over plain HTTP by default"),
    M("cookie-httponly-off", "config/settings/base.py",
      "SESSION_COOKIE_HTTPONLY = True", "SESSION_COOKIE_HTTPONLY = False", ["apps/core/tests/test_audit_gaps.py"],
      "script can read the session cookie"),
    M("cookie-samesite-none", "config/settings/base.py",
      'SESSION_COOKIE_SAMESITE = "Lax"', 'SESSION_COOKIE_SAMESITE = "None"', ["apps/core/tests/test_audit_gaps.py"],
      "the session cookie is sent on cross-site requests"),
    M("scope-timeseries", "apps/analytics/selectors.py",
      "        for row in incidents_in(user, window)\n        .annotate(day=",
      "        for row in Incident.objects.all()\n        .annotate(day=", ["apps/core/tests/test_audit_gaps.py"],
      "the incidents-per-day chart counts every team's incidents"),
    M("scope-sessions-list", "apps/security/views.py",
      'return SessionRecord.objects.filter(user=actor(self.request)).order_by("-created_at", "-id")',
      'return SessionRecord.objects.all().order_by("-created_at", "-id")', ["apps/core/tests/test_audit_gaps.py"],
      "the session list shows other people's sessions"),
    M("reset-ends-sessions", "apps/security/views.py",
      "            ended = sessions.revoke(user)  # whoever had the old password is out",
      "            ended = 0", SEC, "a password reset leaves the attacker's session alive"),
    M("audit-append-only-trigger", "apps/security/migrations/0002_audit_append_only.py",
      "    operations = [migrations.RunSQL(FORWARD, REVERSE)]", "    operations = []", SEC,
      "the database lets audit rows be rewritten", create_db=True),
    M("key-grace-expiry", "apps/catalog/actions.py",
      "            | Q(previous_key_hash=digest, previous_key_expires_at__gt=now or timezone.now())",
      "            | Q(previous_key_hash=digest)", ["apps/catalog/tests"],
      "a rotated-out key works forever"),
    M("csp-enforced", "config/settings/base.py",
      'SECURE_CSP = _CSP_POLICY if CSP_MODE == "enforce" else {}', "SECURE_CSP = {}", SEC,
      "no Content-Security-Policy on Django pages"),
    M("admin-password-only-login", "config/urls.py",
      "admin.site.login = admin_login  # type: ignore[method-assign,assignment]", "", SEC,
      "the Django admin accepts a password without MFA"),
    # --- API contract (production-readiness, phase 5) -------------------------------------
    M("cursor-tiebreak", "apps/incidents/views.py",
      'ordering = ("-triggered_at", "-id")', 'ordering = ("-triggered_at",)', [API],
      "a cursor over tied timestamps skips and repeats incidents"),
    M("api-404-json", "config/urls.py",
      'handler404 = "apps.core.api_errors.not_found"', "", [API],
      "unknown /api/ paths answer with an HTML page"),
    M("body-limit-early", "apps/core/api_errors.py",
      "            if length > limit:", "            if False:", [API],
      "oversized bodies reach the throttle and the view before being refused"),
    M("throttle-fail-open-narrow", "apps/core/throttling.py",
      "        except CACHE_ERRORS as exc:", "        except Exception as exc:", [API],
      "any error inside a throttle (not just a cache outage) waves the request through"),
    M("query-param-validation", "apps/core/params.py",
      "    if unknown := sorted(set(values) - allowed):",
      "    if unknown := sorted(set(values) - allowed) and False:", [API],
      "a misspelt filter silently returns every incident, or none"),
    M("idempotency-replay", "apps/core/idempotency.py",
      "            if stored is not None:\n                return _replay(stored, fingerprint)",
      "            if False:\n                return _replay(stored, fingerprint)", [API],
      "a retried write with the same Idempotency-Key acts twice"),
    M("idem-recheck", "apps/core/idempotency.py",
      "                stored = cache.get(stored_key)\n                if stored is not None:\n                    cache.delete(lock_key)",
      "                stored = None\n                if stored is not None:\n                    cache.delete(lock_key)",
      ["apps/core/tests/test_audit_round3.py"], "a retry that raced the first attempt runs the write twice"),
    M("idem-transient-stored", "apps/core/idempotency.py",
      "TRANSIENT = {408, 409, 425, 429}", "TRANSIENT = set()",
      ["apps/core/tests/test_audit_round3.py"], "a stored 429 is replayed for 24 hours"),
    M("idem-query-string", "apps/core/idempotency.py",
      "target = f\"{request.path}?{request.META.get('QUERY_STRING', '')}\"", "target = request.path",
      ["apps/core/tests/test_audit_round3.py"], "?force=1 replays the plain call's response"),
    M("maintenance-mode-stale", "apps/alerting/actions.py",
      "in_maintenance = _mode_in_force(service) == Service.Mode.MAINTENANCE",
      "in_maintenance = service.mode == Service.Mode.MAINTENANCE",
      ["apps/alerting/tests/test_maintenance_race.py"],
      "an alert arriving as maintenance ends opens a maintenance incident and never pages"),
    M("reserved-dedup-key", "apps/alerting/serializers.py",
      'if value == "__maintenance__":', "if False:", ["apps/core/tests/test_audit_round3.py"],
      "a monitor can name the reserved maintenance dedup key"),
    M("csrf-envelope", "apps/core/api_errors.py",
      "    if _is_api(request):\n        return envelope(\"csrf_failed\"", "    if False:\n        return envelope(\"csrf_failed\"",
      ["apps/core/tests/test_audit_round3.py"], "a CSRF failure under /api/ is an HTML page"),
    M("scoped-pk-field", "apps/core/scoping.py",
      "        return scope_to_teams(queryset, request.user, self.team_lookup)", "        return queryset",
      ["apps/core/tests/test_audit_round3.py"], "a body naming another team's object differs from an unknown id"),
    M("scoped-filter", "apps/core/scoping.py",
      "scope_to_teams(\n            model._default_manager.all(), request.user, team_lookup\n        )",
      "model._default_manager.all()",
      ["apps/core/tests/test_audit_round3.py"], "a filter naming another team's object differs from an unknown id"),
    M("removed-member-paged", "apps/escalations/engine.py",
      "        candidates = candidates.filter(memberships__team_id=team_id)", "        pass",
      ["apps/escalations/tests/test_removed_members.py"], "a person removed from a team is still paged by it"),
    M("retry-claim-gate", "apps/notifications/actions.py",
      "        if notification.next_attempt_at is not None and now < notification.next_attempt_at:",
      "        if False:", ["apps/notifications/tests/test_delivery_claim.py"],
      "a failed page is retried at once, spending its attempts in seconds"),
    M("retry-delay-recorded", "apps/notifications/actions.py",
      "        notification.next_attempt_at = now + retry_delay(notification.attempts)",
      "        notification.next_attempt_at = None", ["apps/notifications/tests/test_delivery_claim.py"],
      "no retry delay is recorded after a failed attempt"),
    M("counter-atomic", "apps/core/ratelimit.py",
      '    if isinstance(caches["default"], DatabaseCache):', "    if False:",
      ["apps/core/tests/test_counters.py"], "database-cache counters lose increments under concurrency"),
    M("failed-recent-window", "apps/core/metrics.py",
      "status=Notification.Status.FAILED, updated_at__gte=now - timedelta(minutes=15)",
      "status=Notification.Status.FAILED, updated_at__gte=now - timedelta(days=365)",
      ["apps/core/tests/test_observability.py"], "the failure alert counts rows the retention purge will delete"),
    M("idempotency-caller-scope", "apps/core/idempotency.py",
      '        return f"user:{user.pk}"', '        return "user"', [API],
      "one user's Idempotency-Key replays another user's response"),
    M("secret-response-tombstone", "apps/core/idempotency.py",
      '                if "no-store" in response.get("Cache-Control", ""):',
      "                if False:", ["apps/security/tests/test_secret_responses.py"],
      "integration keys, MFA secrets and backup codes are written to Redis for replay"),
    M("integration-key-no-store", "apps/catalog/views.py",
      '        if isinstance(response.data, dict) and response.data.get("integration_key"):',
      "        if False:", ["apps/security/tests/test_secret_responses.py"],
      "a freshly issued integration key may be cached by browsers, proxies and the replay store"),
    M("request-id-500", "apps/core/api_errors.py",
      "        request_id = get_request_id()",
      '        request_id = request.headers.get("X-Request-ID", "")', [API],
      "the 500 body echoes raw header input instead of the id the logs carry"),
    # --- deployment and demo mode (production-readiness, phase 6) --------------------------
    M("tick-secret-check", "apps/core/tick.py",
      "    if not hmac.compare_digest(supplied.encode(), settings.TICK_SECRET.encode()):",
      "    if False:", [DEMO], "anyone can run the tick without the secret"),
    M("tick-off-by-default", "apps/core/tick.py",
      "    if not (settings.DEMO_MODE and settings.TICK_SECRET):",
      "    if not settings.DEMO_MODE:", [DEMO], "an empty TICK_SECRET opens the tick to everyone"),
    M("tick-rate-limit", "apps/core/tick.py",
      '    if not ratelimit.allow("tick", request, limit=RATE_LIMIT_PER_MINUTE):',
      "    if False:", [DEMO], "the tick secret can be guessed at full speed"),
    M("inline-eta-guard", "apps/core/dispatch.py",
      "    if eta is not None and eta > timezone.now():", "    if False:", [DEMO],
      "demo mode runs future work (an escalation, a delayed step) immediately"),
    M("counter-expiry-pin", "apps/core/ratelimit.py",
      "    cache.touch(key, timeout=remaining)", "    pass",
      ["apps/core/tests/test_counters.py"],
      "on the database cache a 15-minute lockout lasts 5 minutes"),
    M("demo-account-guard", "apps/core/demo.py",
      "            settings.DEMO_ACCOUNT_GUARD\n", "            False\n", [DEMO],
      "a visitor can turn on MFA for a shared demo login and lock everyone out"),
    M("spa-csp", "apps/core/spa.py",
      "    return csp_override(policy)(view)", "    return view", [DEMO],
      "the SPA served by Django gets the nonce policy (or none) instead of its own"),
]


def run_pytest(args: list[str], create_db: bool) -> tuple[int, str, float]:
    env = dict(os.environ)
    env.pop("UV_NATIVE_TLS", None)
    cmd = ["uv", "run", "pytest", "-q", "-x", "--no-cov", "-p", "no:cacheprovider",
           "--tb=line", *args]
    if create_db:
        cmd.append("--create-db")
    start = time.time()
    try:
        proc = subprocess.run(cmd, cwd=BACKEND, env=env, capture_output=True, text=True,
                              timeout=int(os.environ.get("MUTATE_TIMEOUT", "300")), check=False)
    except subprocess.TimeoutExpired:
        return 124, "timeout (a hang counts as caught)", time.time() - start
    tail = [ln for ln in proc.stdout.splitlines() if ln.startswith(("FAILED", "ERROR"))
            or " passed" in ln or " failed" in ln]
    return proc.returncode, (tail[-1] if tail else proc.stdout[-200:]), time.time() - start


def apply(m: M) -> str | None:
    path = BACKEND / m.file
    original = path.read_text()
    if original.count(m.old) != 1:
        raise SystemExit(f"[{m.name}] BAD MUTATION: pattern found {original.count(m.old)}x in {m.file}")
    path.write_text(original.replace(m.old, m.new))
    return original


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--only", help="comma-separated mutation names")
    parser.add_argument("--full", action="store_true", help="run the whole suite on survivors")
    parser.add_argument("--json", help="write results to this file")
    args = parser.parse_args()

    chosen = [m for m in MUTATIONS if not args.only or m.name in args.only.split(",")]
    if args.list:
        for m in chosen:
            print(f"{m.name:24} {m.file}  — {m.why}")
        return 0

    results = []
    for m in chosen:
        original = apply(m)
        try:
            rc, detail, secs = run_pytest(m.tests, m.create_db)
            # pytest exit codes: 0 pass, 1 tests failed, 2 interrupted/collection error, 5 none
            # collected. Only a real test failure (or a hang) is evidence the suite noticed; an
            # import error means the mutation was malformed, not that a guard works.
            if rc == 0:
                verdict = "SURVIVED"
            elif rc in (1, 124):
                verdict = "CAUGHT"
            else:
                verdict = "INVALID"
            if rc == 0 and args.full:
                rc2, detail2, secs2 = run_pytest(["--deselect", "apps/core/tests/test_simulation.py"],
                                                 m.create_db)
                verdict = "CAUGHT (full suite)" if rc2 != 0 else "SURVIVED"
                detail, secs = f"{detail}; full: {detail2}", secs + secs2
        finally:
            (BACKEND / m.file).write_text(original)
            if m.create_db:
                run_pytest(["apps/core/tests/test_health.py", "-k", "readyz_reports"], True)  # rebuild clean db
        results.append({"name": m.name, "file": m.file, "why": m.why, "verdict": verdict,
                        "detail": detail, "seconds": round(secs, 1), "equivalent": m.equivalent})
        print(f"{verdict:20} {m.name:24} {detail[:110]}  ({secs:.0f}s)", flush=True)

    invalid = [r for r in results if r["verdict"] == "INVALID"]
    for r in invalid:
        print(f"  INVALID  {r['name']}: pytest could not run it ({r['detail'][:100]}); fix the mutation")
    survivors = [r for r in results if r["verdict"] == "SURVIVED"]
    caught = [r for r in results if r["verdict"].startswith("CAUGHT")]
    print(f"\n{len(caught)} caught, {len(survivors)} survived, {len(invalid)} invalid of {len(results)}")
    for r in survivors:
        print(f"  SURVIVED {r['name']}: {r['why']}" + (f"  [equivalent: {r['equivalent']}]" if r["equivalent"] else ""))
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2))
    unexplained = [r for r in survivors if not r["equivalent"]]
    return 1 if unexplained or invalid else 0


if __name__ == "__main__":
    sys.exit(main())
