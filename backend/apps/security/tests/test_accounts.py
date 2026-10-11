"""Password reset and change, sign-in lockout, sessions, the audit log, and response headers."""

import re
from datetime import timedelta
from unittest import mock

import pytest
import time_machine
from django.core import mail
from django.db import connection, transaction
from django.db.utils import DatabaseError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.security import passwords
from apps.security.models import AuditEvent, SessionRecord

from .conftest import PASSWORD, login

pytestmark = pytest.mark.django_db

NEW_PASSWORD = "an entirely new passphrase 9"


@pytest.fixture
def send_now():
    """Run the reset-email task inline instead of through the broker."""

    def fake_apply_async(args=(), kwargs=None, **_):
        passwords.send_reset_email.run(*args)

    with mock.patch.object(passwords.send_reset_email, "apply_async", fake_apply_async):
        yield


def reset_link_parts(body: str) -> tuple[str, str]:
    match = re.search(r"uid=([\w-]+)&token=([\w-]+)", body)
    assert match, body
    return match.group(1), match.group(2)


def request_reset(email: str, client: APIClient | None = None):
    return (client or APIClient()).post(
        "/api/v1/auth/password-reset/", {"email": email}, format="json"
    )


# --- reset --------------------------------------------------------------------------------------


def test_reset_answers_the_same_whether_or_not_the_account_exists(
    member, send_now, django_capture_on_commit_callbacks
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        known = request_reset(member.email)
        unknown = request_reset("nobody@example.com")
    assert (known.status_code, unknown.status_code) == (204, 204)
    assert known.content == unknown.content
    assert [m.to for m in mail.outbox] == [[member.email]]


def test_a_reset_link_sets_the_password_works_once_and_ends_every_session(
    member, send_now, django_capture_on_commit_callbacks
) -> None:
    signed_in = APIClient()
    assert login(signed_in, member.email).status_code == 200
    with django_capture_on_commit_callbacks(execute=True):
        request_reset(member.email)
    uid, token = reset_link_parts(mail.outbox[0].body)
    body = {"uid": uid, "token": token, "new_password": NEW_PASSWORD}

    assert (
        APIClient().post("/api/v1/auth/password-reset/confirm/", body, format="json").status_code
        == 204
    )
    assert signed_in.get("/api/v1/me/").status_code == 403, "old sessions must end"
    assert SessionRecord.objects.filter(user=member).count() == 0
    assert login(APIClient(), member.email, NEW_PASSWORD).status_code == 200
    reused = APIClient().post(
        "/api/v1/auth/password-reset/confirm/",
        {**body, "new_password": "yet another long one 77"},
        format="json",
    )
    assert reused.status_code == 400, "a reset link is single-use"


def test_a_reset_link_expires(
    member, send_now, django_capture_on_commit_callbacks, settings
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        request_reset(member.email)
    uid, token = reset_link_parts(mail.outbox[0].body)
    with time_machine.travel(
        timezone.now() + timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT + 60)
    ):
        response = APIClient().post(
            "/api/v1/auth/password-reset/confirm/",
            {"uid": uid, "token": token, "new_password": NEW_PASSWORD},
            format="json",
        )
    assert response.status_code == 400


@pytest.mark.parametrize("weak", ["short", "password1234", "123456789012", "on-call"])
def test_weak_passwords_are_refused(
    member, send_now, django_capture_on_commit_callbacks, weak: str
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        request_reset(member.email)
    uid, token = reset_link_parts(mail.outbox[0].body)
    response = APIClient().post(
        "/api/v1/auth/password-reset/confirm/",
        {"uid": uid, "token": token, "new_password": weak},
        format="json",
    )
    assert response.status_code == 422


def test_forged_or_mangled_reset_tokens_are_refused(member) -> None:
    for uid, token in (("MQ", "bogus-token"), ("!!", "x"), ("", "")):
        response = APIClient().post(
            "/api/v1/auth/password-reset/confirm/",
            {"uid": uid or "x", "token": token or "x", "new_password": NEW_PASSWORD},
            format="json",
        )
        assert response.status_code == 400
    assert member.check_password(PASSWORD)


def test_deactivated_accounts_get_no_reset_email(
    member, send_now, django_capture_on_commit_callbacks
) -> None:
    member.is_active = False
    member.save()
    with django_capture_on_commit_callbacks(execute=True):
        assert request_reset(member.email).status_code == 204
    assert mail.outbox == []


def test_one_address_gets_at_most_three_reset_emails_an_hour(
    member, send_now, django_capture_on_commit_callbacks
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        for _ in range(6):
            assert request_reset(member.email).status_code == 204
    assert len(mail.outbox) == 3


# --- change -------------------------------------------------------------------------------------


def test_changing_the_password_keeps_this_session_and_ends_the_others(member) -> None:
    this, other = APIClient(), APIClient()
    login(this, member.email)
    login(other, member.email)
    response = this.post(
        "/api/v1/me/password/",
        {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        format="json",
    )
    assert response.status_code == 204
    assert this.get("/api/v1/me/").status_code == 200
    assert other.get("/api/v1/me/").status_code == 403


def test_changing_the_password_needs_the_current_one_and_a_strong_new_one(member) -> None:
    client = APIClient()
    login(client, member.email)
    assert (
        client.post(
            "/api/v1/me/password/",
            {"current_password": "nope", "new_password": NEW_PASSWORD},
            format="json",
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/me/password/",
            {"current_password": PASSWORD, "new_password": "short"},
            format="json",
        ).status_code
        == 422
    )
    member.refresh_from_db()
    assert member.check_password(PASSWORD)


# --- lockout ------------------------------------------------------------------------------------


def test_an_account_locks_after_ten_failures_from_anywhere(member, settings) -> None:
    for i in range(settings.LOGIN_LOCKOUT_FAILURES):
        response = login(APIClient(), member.email, "wrong", REMOTE_ADDR=f"10.0.0.{i + 1}")
        assert response.status_code in (401, 429)
    locked = login(APIClient(), member.email, PASSWORD, REMOTE_ADDR="10.9.9.9")
    assert locked.status_code == 429, "even the right password, from a new address, is refused"
    assert locked.json()["error"]["code"] == "too_many_attempts"
    with time_machine.travel(
        timezone.now() + timedelta(seconds=settings.LOGIN_LOCKOUT_SECONDS + 1)
    ):
        from django.core.cache import cache

        cache.clear()  # the locmem test cache has no notion of the travelled clock
        assert login(APIClient(), member.email).status_code == 200


def test_unknown_accounts_lock_the_same_way_so_lockout_reveals_nothing(settings) -> None:
    for i in range(settings.LOGIN_LOCKOUT_FAILURES):
        login(APIClient(), "ghost@example.com", "wrong", REMOTE_ADDR=f"10.0.1.{i + 1}")
    assert (
        login(APIClient(), "ghost@example.com", "wrong", REMOTE_ADDR="10.0.2.1").status_code == 429
    )


def test_a_successful_sign_in_clears_the_failure_count(member, settings) -> None:
    for i in range(settings.LOGIN_LOCKOUT_FAILURES - 1):
        login(APIClient(), member.email, "wrong", REMOTE_ADDR=f"10.0.3.{i + 1}")
    assert login(APIClient(), member.email, REMOTE_ADDR="10.0.4.1").status_code == 200
    for i in range(settings.LOGIN_LOCKOUT_FAILURES - 1):
        login(APIClient(), member.email, "wrong", REMOTE_ADDR=f"10.0.5.{i + 1}")
    assert login(APIClient(), member.email, REMOTE_ADDR="10.0.6.1").status_code == 200


# --- sessions -----------------------------------------------------------------------------------


def test_sessions_can_be_listed_and_revoked(member) -> None:
    laptop, phone = APIClient(), APIClient()
    login(laptop, member.email, HTTP_USER_AGENT="laptop")
    login(phone, member.email, HTTP_USER_AGENT="phone")
    listed = laptop.get("/api/v1/me/sessions/").json()
    assert {s["user_agent"] for s in listed} == {"laptop", "phone"}
    assert [s["current"] for s in listed if s["user_agent"] == "laptop"] == [True]

    phone_id = next(s["id"] for s in listed if s["user_agent"] == "phone")
    assert laptop.delete(f"/api/v1/me/sessions/{phone_id}/").status_code == 204
    assert phone.get("/api/v1/me/").status_code == 403
    assert laptop.get("/api/v1/me/").status_code == 200


def test_sign_out_everywhere_else(member) -> None:
    clients = [APIClient() for _ in range(3)]
    for c in clients:
        login(c, member.email)
    assert clients[0].post("/api/v1/me/sessions/revoke-others/").json() == {"count": 2}
    assert [c.get("/api/v1/me/").status_code for c in clients] == [200, 403, 403]


def test_you_cannot_see_or_end_someone_elses_session(member, people) -> None:
    theirs = APIClient()
    login(theirs, member.email)
    record = SessionRecord.objects.get(user=member)
    other = APIClient()
    other.force_login(people.admin)
    assert other.delete(f"/api/v1/me/sessions/{record.pk}/").status_code == 404
    assert theirs.get("/api/v1/me/").status_code == 200


def test_sessions_have_an_absolute_lifetime(member, settings) -> None:
    client = APIClient()
    login(client, member.email)
    with time_machine.travel(timezone.now() + timedelta(seconds=settings.SESSION_COOKIE_AGE + 60)):
        assert client.get("/api/v1/me/").status_code == 403


# --- audit log ----------------------------------------------------------------------------------


def test_sign_ins_and_failures_are_audited(member) -> None:
    login(APIClient(), member.email, "wrong")
    login(APIClient(), member.email)
    actions = list(AuditEvent.objects.order_by("id").values_list("action", flat=True))
    assert actions[-2:] == ["auth.login_failed", "auth.login"]
    failed = AuditEvent.objects.get(action="auth.login_failed")
    assert failed.data["attempted_email"] == member.email
    assert "wrong" not in str(failed.data), "passwords never reach the audit log"


def test_admin_changes_are_audited_with_their_team(people, service) -> None:
    client = APIClient()
    client.force_login(people.admin)
    client.patch(f"/api/v1/services/{service.pk}/", {"description": "x"}, format="json")
    client.post(f"/api/v1/services/{service.pk}/rotate-key/")
    events = AuditEvent.objects.filter(team_id=service.team_id).values_list(
        "action", "actor_id", "target_id"
    )
    assert ("service.updated", people.admin.pk, str(service.pk)) in events
    assert ("service.key_rotated", people.admin.pk, str(service.pk)) in events


def test_the_audit_log_is_append_only_in_the_database(member) -> None:
    login(APIClient(), member.email)
    event = AuditEvent.objects.latest("id")
    with pytest.raises(RuntimeError):
        event.save()
    with pytest.raises(RuntimeError):
        event.delete()
    for sql in ("UPDATE security_auditevent SET action = 'x'", "DELETE FROM security_auditevent"):
        with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
            connection.cursor().execute(sql)
    assert AuditEvent.objects.filter(pk=event.pk, action=event.action).exists()


def test_team_admins_see_only_their_teams_events_and_responders_none(people, service) -> None:
    AuditEvent.objects.create(action="x.mine", team_id=service.team_id)
    AuditEvent.objects.create(action="x.other", team_id=service.team_id + 999)
    admin = APIClient()
    admin.force_login(people.admin)
    actions = {e["action"] for e in admin.get("/api/v1/audit-events/").json()["results"]}
    assert "x.mine" in actions
    assert "x.other" not in actions
    responder = APIClient()
    responder.force_login(people.on_call)
    assert responder.get("/api/v1/audit-events/").json()["results"] == []


# --- headers ------------------------------------------------------------------------------------


def test_django_pages_carry_csp_and_the_other_headers(client) -> None:
    response = client.get("/a/not-a-token/")
    csp = response["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    nonce = re.search(r"'nonce-([^']+)'", csp)
    assert nonce, csp
    assert f'nonce="{nonce.group(1)}"'.encode() in response.content, (
        "the inline style must carry the nonce"
    )
    assert "camera=()" in response["Permissions-Policy"]
    assert response["X-Frame-Options"] == "DENY"
    assert response["Referrer-Policy"] in ("no-referrer", "strict-origin-when-cross-origin")
    assert response["Cross-Origin-Opener-Policy"] == "same-origin"


def test_csp_reports_are_accepted_and_not_stored(client) -> None:
    before = AuditEvent.objects.count()
    response = client.post(
        "/api/v1/csp-report/", data=b'{"csp-report":{}}', content_type="application/csp-report"
    )
    assert response.status_code == 204
    assert AuditEvent.objects.count() == before
