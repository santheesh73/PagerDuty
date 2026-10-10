import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import User
from conftest import Paging

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_throttle_counters() -> None:
    cache.clear()


def test_login_with_valid_credentials_starts_a_session(
    api_client: APIClient, people: Paging
) -> None:
    response = api_client.post(
        "/api/v1/auth/login/",
        {"email": people.on_call.email.upper(), "password": "demo1234"},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["email"] == people.on_call.email
    assert api_client.get("/api/v1/me/").status_code == 200


def test_login_with_a_wrong_password_is_401(api_client: APIClient, people: Paging) -> None:
    response = api_client.post(
        "/api/v1/auth/login/", {"email": people.on_call.email, "password": "nope"}, format="json"
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_login_requires_csrf(people: Paging) -> None:
    client = APIClient(enforce_csrf_checks=True)
    response = client.post(
        "/api/v1/auth/login/",
        {"email": people.on_call.email, "password": "demo1234"},
        format="json",
    )
    assert response.status_code == 403


def test_csrf_endpoint_sets_the_cookie_for_the_login_page() -> None:
    client = APIClient(enforce_csrf_checks=True)
    assert client.get("/api/v1/auth/csrf/").status_code == 204
    assert "csrftoken" in client.cookies


def test_session_writes_require_the_csrf_header(people: Paging) -> None:
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(people.on_call)
    assert client.post("/api/v1/notifications/read-all/").status_code == 403
    token = client.get("/api/v1/me/").cookies["csrftoken"].value
    assert (
        client.post("/api/v1/notifications/read-all/", headers={"X-CSRFToken": token}).status_code
        == 200
    )


def test_login_is_throttled(api_client: APIClient, people: Paging) -> None:
    codes = [
        api_client.post(
            "/api/v1/auth/login/", {"email": "x@y.z", "password": "bad"}, format="json"
        ).status_code
        for _ in range(11)
    ]
    assert codes[-1] == 429


def test_anonymous_requests_get_the_error_envelope(api_client: APIClient) -> None:
    response = api_client.get("/api/v1/incidents/")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_authenticated"


def test_me_lists_memberships_and_logout_ends_the_session(
    api_client: APIClient, people: Paging
) -> None:
    api_client.force_login(people.admin)
    me = api_client.get("/api/v1/me/").json()
    assert me["memberships"][0]["role"] == "admin"

    assert api_client.post("/api/v1/auth/logout/").status_code == 204
    assert api_client.get("/api/v1/me/").status_code == 403


def test_me_can_update_name_and_timezone_but_not_email(
    api_client: APIClient, people: Paging
) -> None:
    api_client.force_login(people.on_call)
    response = api_client.patch(
        "/api/v1/me/", {"timezone": "Europe/London", "email": "x@y.z"}, format="json"
    )
    assert response.status_code == 200
    user = User.objects.get(pk=people.on_call.pk)
    assert user.timezone == "Europe/London"
    assert user.email == people.on_call.email


def test_teams_and_users_are_scoped_to_your_teams(api_client: APIClient, people: Paging) -> None:
    from tests.factories import MembershipFactory

    outsider = MembershipFactory().user
    api_client.force_login(people.on_call)
    teams = api_client.get("/api/v1/teams/").json()
    users = {u["id"] for u in api_client.get("/api/v1/users/").json()}

    assert len(teams) == 1
    assert outsider.pk not in users
    members = api_client.get(f"/api/v1/teams/{teams[0]['id']}/members/").json()
    assert {m["role"] for m in members} == {"admin", "responder", "viewer"}
