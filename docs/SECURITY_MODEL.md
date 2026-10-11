# Security model

What protects a Pulse account and its data, what each control is proven by, and what is not built.

## Signing in

| Control | Behaviour | Proof |
|---|---|---|
| Password policy | 12+ characters, not common, not all digits, not similar to your name/email (Django validators) on reset, change and `createsuperuser`. The seeded demo accounts (`demo1234`) bypass it and are for demos only. | `security/tests/test_accounts.py::test_weak_passwords_are_refused` |
| Per-address throttle | 10 sign-in attempts/minute per client address (`NUM_PROXIES`-aware) | existing auth tests |
| Per-account lockout | 10 failures in 15 minutes and the account refuses even the right password, from any address, until the window ends. Unknown emails lock the same way, so lockout reveals nothing about who has an account. Trade-off: anyone can lock an account for 15 minutes by guessing. | `test_an_account_locks_after_ten_failures_from_anywhere`; mutation `login-lockout` |
| MFA (TOTP) | RFC 6238, 30 s, ±1 step for clock drift; each code (time step) is accepted **once**. With MFA on, the password step returns `{"mfa_required": true}` and does **not** authenticate; the code step (`/auth/mfa/`) must follow within 5 minutes, with at most 5 wrong codes before you start over. The session id changes at each step. | `test_totp.py` (RFC 4226/6238 vectors), `test_mfa.py`; mutations `mfa-login-gate`, `totp-replay`, `mfa-attempt-limit` |
| Backup codes | 10 single-use codes shown once at enrolment (and on regeneration, which invalidates the old set); stored as keyed hashes. | `test_backup_codes_work_once_each`; mutation `backup-code-single-use` |
| Admins must use MFA | `REQUIRE_MFA_FOR_ADMINS` (on in production settings): a team admin or staff user without MFA can reach only their profile and the MFA enrolment endpoints; the API answers `mfa_enrollment_required` and the SPA routes them to enrolment. They cannot switch it off. | `test_admins_must_enrol_before_doing_anything_else`; mutation `mfa-enrolment-gate` |
| Django admin | Its password-only login form is replaced by a redirect to the app's sign-in, so the admin gets the same lockout, MFA and audit trail. | `test_the_django_admin_login_form_is_replaced_by_the_app_login`; mutation `admin-password-only-login` |
| OIDC / SSO | **Not built.** Pulse authenticates with its own accounts only. | n/a |

## Passwords and sessions

- **Reset** (`/auth/password-reset/`) always answers 204, sends the email from a background task (so
  timing does not depend on SMTP), and sends at most 3 emails per address per hour. The link (Django's
  token: it embeds the password hash and last login) expires after an hour and stops working once used.
  Completing a reset **ends every session** of that account.
- **Change** (`/me/password/`) needs the current password; it keeps the current session and ends all others.
- **Sessions** have an absolute lifetime (`SESSION_HOURS`, default 12) and are listed at
  `/me/sessions/` with address and browser; any of them can be signed out, or all but this one.
  Session cookies are `HttpOnly`, `SameSite=Lax`, `Secure` and named `__Host-sessionid` in production.

## Integration keys

Only a SHA-256 of each service's Events API key is stored (`catalog/models.py`). The key is returned
once, in the response that created or rotated it; after that the API shows an 8-character prefix. A
rotation keeps the previous key working for `INTEGRATION_KEY_GRACE_HOURS` (24) so monitoring configs can
be updated without dropping alerts; rotating again (or a zero-grace rotation) retires it at once. The
migration hashed every existing key, so live integrations kept working
(`catalog/tests/test_key_migration.py`). `manage.py routing_key <service>` now *issues* a key.

## Audit log

`security_auditevent` records sign-ins (and failures, with the attempted email, never the password),
MFA changes, backup-code use, password resets and changes, session revocations, contact/webhook changes,
and every create/update/delete of services, escalation policies, schedules and overrides, plus key
rotations. It is **append-only in Postgres**: a trigger rejects UPDATE and DELETE from anyone, including
the app and the admin; there are no foreign keys, so records outlive what they describe. Team admins
read their teams' events at `/api/v1/audit-events/` (and in the app under *Audit log*); staff read all,
also in the Django admin (read-only). Proof: `test_the_audit_log_is_append_only_in_the_database`;
mutation `audit-append-only-trigger`.

## Headers

| Header | Django pages (API, admin, action links) | SPA (nginx) |
|---|---|---|
| Content-Security-Policy | `default-src 'self'`, scripts and styles by per-request nonce, `frame-ancestors 'none'`, `object-src 'none'`, `base-uri 'none'`; the Swagger page alone allows its CDN | `script-src 'self'`; `style-src 'self' 'unsafe-inline'` (React/Recharts style attributes); same framing/object/base rules |
| Mode | `CSP_MODE=enforce` (default) or `report-only`; reports go to `/api/v1/csp-report/` (logged, rate limited) | same variable on the web container |
| HSTS | 1 year by default in production (`SECURE_HSTS_SECONDS`); subdomains/preload opt-in | sent by Django on every API response over HTTPS |
| Others | `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Cross-Origin-Opener-Policy: same-origin`, `Permissions-Policy` denying camera, microphone, geolocation, payment... | same |

`manage.py check --deploy` with production settings reports no issues; the two HSTS checks for
subdomains and preload are silenced only while those stay off (`config/settings/prod.py`).

## Not verified

- No penetration test or third-party review.
- The SPA's CSP is verified by `make doctor` (header present) and the Playwright journey (the app works
  under it) in CI, not in every browser.
- TOTP secrets and webhook signing secrets are stored in the clear (they must be, to compute codes and
  signatures); encryption at rest is the database's job here.
