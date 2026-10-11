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
      "require_role(self.request.user, schedule.team_id, Role.VIEWER)\n        return schedule",
      "return schedule", MATRIX, "overrides readable across teams"),
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
    M("skip-locked", "apps/escalations/engine.py", "select_for_update(skip_locked=True, of=",
      "select_for_update(of=", ["apps/escalations/tests/test_engine.py"],
      "blocking lock instead of skip-locked",
      equivalent="A blocking lock re-checks the guarded filter once it acquires the row, so "
      "behaviour is the same; skip_locked is a latency optimisation (callers never wait)."),
    M("dedup-index", "apps/incidents/migrations/0001_initial.py",
      'condition=models.Q(("status", "resolved"), _negated=True),',
      'condition=models.Q(("status", "never-a-status")),',
      ["apps/alerting/tests/test_ingest.py"], "partial unique index no longer enforces dedup",
      create_db=True),
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
      "Incident.objects.select_for_update(of=(\"self\",))\n        .select_related(\"service\")",
      "Incident.objects\n        .select_related(\"service\")",
      ["apps/incidents/tests/test_locking.py"], "incident actions no longer serialise"),
    M("ingest-advisory-lock", "apps/alerting/actions.py",
      'advisory_xact_lock("incident-key", service.pk, incident_key)', "pass",
      ["apps/alerting/tests/test_ingest_churn.py"], "open-or-attach no longer serialised per key"),
    M("ingest-row-lock", "apps/alerting/actions.py",
      "Incident.objects.select_for_update(of=(\"self\",))\n                    .filter(service=service",
      "Incident.objects\n                    .filter(service=service",
      ["apps/incidents/tests/test_locking.py"], "attach can overtake a resolve"),
    M("deliver-claim-lock", "apps/notifications/actions.py",
      "        notification = (\n            Notification.objects.select_for_update(of=(\"self\",))\n"
      "            .select_related(\"incident__service\", \"user\")",
      "        notification = (\n            Notification.objects\n"
      "            .select_related(\"incident__service\", \"user\")",
      ["apps/notifications/tests/test_delivery_claim.py"], "two workers can claim one page"),
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
      "        return int(cache.get(_lockout_key(email)) or 0) >= settings.LOGIN_LOCKOUT_FAILURES",
      "        return False", SEC, "no per-account lockout"),
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
