"""Two-factor sign-in, enrolment, backup codes, and the admin enrolment gate."""

import time
from datetime import timedelta

import pytest
import time_machine
from django.utils import timezone
from rest_framework.test import APIClient

from apps.security.models import AuditEvent, BackupCode, MfaDevice

from .conftest import PASSWORD, enrol, login, next_code

pytestmark = pytest.mark.django_db


@pytest.fixture
def enrolled(member):
    client = APIClient()
    assert login(client, member.email).status_code == 200
    secret, codes = enrol(client)
    return member, secret, codes


def test_enrolment_returns_backup_codes_once_and_stores_only_hashes(member) -> None:
    client = APIClient()
    login(client, member.email)
    assert client.get("/api/v1/me/mfa/").json() == {
        "enabled": False,
        "enforced": False,
        "backup_codes_remaining": 0,
    }
    _secret, codes = enrol(client)
    assert len(codes) == 10
    assert client.get("/api/v1/me/mfa/").json()["enabled"] is True
    stored = list(BackupCode.objects.filter(user=member).values_list("code_hash", flat=True))
    assert not any(code.replace("-", "") in h for code in codes for h in stored)
    assert AuditEvent.objects.filter(action="mfa.enabled", actor_id=member.pk).exists()


def test_a_wrong_code_does_not_enable_mfa(member) -> None:
    client = APIClient()
    login(client, member.email)
    client.post("/api/v1/me/mfa/setup/")
    assert (
        client.post("/api/v1/me/mfa/confirm/", {"code": "000000"}, format="json").status_code == 422
    )
    assert not MfaDevice.objects.get(user=member).enabled


def test_setup_is_refused_while_mfa_is_on(enrolled) -> None:
    member, *_ = enrolled
    client = APIClient()
    client.force_login(member)
    assert client.post("/api/v1/me/mfa/setup/").status_code == 409


def test_password_alone_no_longer_signs_in(enrolled) -> None:
    member, secret, _ = enrolled
    client = APIClient()
    step_one = login(client, member.email)
    assert step_one.status_code == 200
    assert step_one.json() == {"mfa_required": True}
    assert client.get("/api/v1/me/").status_code == 403, "the password step must not authenticate"

    step_two = client.post("/api/v1/auth/mfa/", {"code": next_code(secret)}, format="json")
    assert step_two.status_code == 200
    assert step_two.json()["email"] == member.email
    assert client.get("/api/v1/me/").status_code == 200


def test_the_session_id_changes_at_each_step(enrolled) -> None:
    member, secret, _ = enrolled
    client = APIClient()
    client.get("/api/v1/auth/csrf/")
    login(client, member.email)
    after_password = client.cookies["sessionid"].value
    client.post("/api/v1/auth/mfa/", {"code": next_code(secret)}, format="json")
    assert client.cookies["sessionid"].value != after_password


def test_a_totp_code_works_once(enrolled) -> None:
    member, secret, _ = enrolled
    code = next_code(secret)
    first = APIClient()
    login(first, member.email)
    assert first.post("/api/v1/auth/mfa/", {"code": code}, format="json").status_code == 200
    second = APIClient()
    login(second, member.email)
    assert second.post("/api/v1/auth/mfa/", {"code": code}, format="json").status_code == 401


def test_backup_codes_work_once_each(enrolled) -> None:
    member, _, codes = enrolled
    for attempt, expected in ((codes[0], 200), (codes[0], 401), (codes[1].upper(), 200)):
        client = APIClient()
        login(client, member.email)
        assert (
            client.post("/api/v1/auth/mfa/", {"code": attempt}, format="json").status_code
            == expected
        )
    assert AuditEvent.objects.filter(action="auth.backup_code_used").count() == 2


def test_five_wrong_codes_send_you_back_to_the_password(enrolled) -> None:
    member, secret, _ = enrolled
    client = APIClient()
    login(client, member.email)
    for _ in range(5):
        assert (
            client.post("/api/v1/auth/mfa/", {"code": "000000"}, format="json").status_code == 401
        )
    expired = client.post("/api/v1/auth/mfa/", {"code": next_code(secret)}, format="json")
    assert expired.status_code == 401
    assert expired.json()["error"]["code"] == "mfa_session_expired"


def test_the_code_step_expires(enrolled) -> None:
    member, secret, _ = enrolled
    client = APIClient()
    login(client, member.email)
    with time_machine.travel(timezone.now() + timedelta(minutes=6)):
        response = client.post("/api/v1/auth/mfa/", {"code": next_code(secret)}, format="json")
    assert response.status_code == 401


def test_the_code_step_without_a_password_step_does_nothing(enrolled) -> None:
    _, secret, _ = enrolled
    response = APIClient().post("/api/v1/auth/mfa/", {"code": next_code(secret)}, format="json")
    assert response.status_code == 401


def test_disabling_needs_both_password_and_code(enrolled) -> None:
    member, secret, _ = enrolled
    client = APIClient()
    client.force_login(member)
    assert (
        client.post(
            "/api/v1/me/mfa/disable/",
            {"password": "wrong", "code": next_code(secret)},
            format="json",
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/me/mfa/disable/", {"password": PASSWORD, "code": "000000"}, format="json"
        ).status_code
        == 422
    )
    ok = client.post(
        "/api/v1/me/mfa/disable/", {"password": PASSWORD, "code": next_code(secret)}, format="json"
    )
    assert ok.status_code == 204
    assert not MfaDevice.objects.filter(user=member).exists()
    assert not BackupCode.objects.filter(user=member).exists()


def test_regenerating_backup_codes_invalidates_the_old_ones(enrolled) -> None:
    member, secret, old = enrolled
    client = APIClient()
    client.force_login(member)
    new = client.post(
        "/api/v1/me/mfa/backup-codes/", {"code": next_code(secret)}, format="json"
    ).json()["backup_codes"]
    assert set(new).isdisjoint(old)
    other = APIClient()
    login(other, member.email)
    assert other.post("/api/v1/auth/mfa/", {"code": old[0]}, format="json").status_code == 401


# --- the admin gate ---------------------------------------------------------------------------


def test_admins_must_enrol_before_doing_anything_else(people, settings) -> None:
    settings.REQUIRE_MFA_FOR_ADMINS = True
    admin = people.admin
    admin.set_password(PASSWORD)
    admin.save()
    client = APIClient()
    assert login(client, admin.email).status_code == 200

    blocked = client.get("/api/v1/incidents/")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "mfa_enrollment_required"
    assert client.get("/admin/").status_code == 403
    assert client.get("/api/v1/me/").status_code == 200  # the SPA can still load and explain

    enrol(client)
    assert client.get("/api/v1/incidents/").status_code == 200


def test_responders_are_not_gated(member, settings) -> None:
    settings.REQUIRE_MFA_FOR_ADMINS = True
    client = APIClient()
    login(client, member.email)
    assert client.get("/api/v1/incidents/").status_code == 200


def test_an_admin_cannot_switch_mfa_off_while_it_is_required(people, settings) -> None:
    admin = people.admin
    admin.set_password(PASSWORD)
    admin.save()
    client = APIClient()
    login(client, admin.email)
    secret, _ = enrol(client)
    settings.REQUIRE_MFA_FOR_ADMINS = True
    response = client.post(
        "/api/v1/me/mfa/disable/", {"password": PASSWORD, "code": next_code(secret)}, format="json"
    )
    assert response.status_code == 403
    assert MfaDevice.objects.filter(user=admin).exists()


def test_the_django_admin_login_form_is_replaced_by_the_app_login(client) -> None:
    response = client.get("/admin/login/")
    assert response.status_code == 302
    assert response["Location"].endswith("/login?next=/admin/")
    posted = client.post("/admin/login/", {"username": "x", "password": "y"})
    assert posted.status_code == 302, "the password-only admin form must not exist"


def test_time_is_real_in_these_tests() -> None:
    assert abs(time.time() - timezone.now().timestamp()) < 5
