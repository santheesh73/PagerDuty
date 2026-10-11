"""Cross-team isolation, enumerated from the real URL table.

Every `/api/v1/` route is walked from Django's resolver (not a hand-kept list), so a new
endpoint cannot be added without being classified here: the completeness test fails until it is
either exercised against another team's objects or listed in EXEMPT with a reason.

Setup: team A owns a full object graph whose names all contain a marker string; the caller is an
admin of team B. For every route and every method it supports:

* routes addressing one of A's objects must answer 403 or 404 and change nothing;
* collection routes must not contain A's marker anywhere in the response, and creating into
  team A must be refused;
* self-scoped routes (notifications) must not expose A's rows.
"""

import re
from dataclasses import dataclass

import pytest
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.test import APIClient

from apps.accounts.models import Membership
from apps.alerting.models import Alert
from apps.incidents.models import Incident
from apps.notifications.models import Notification, NotificationRule
from apps.schedules.models import ScheduleOverride
from apps.security.models import AuditEvent, SessionRecord
from tests.factories import (
    AlertFactory,
    IncidentFactory,
    MembershipFactory,
    NotificationFactory,
    ScheduleFactory,
    ScheduleOverrideFactory,
    ServiceFactory,
    TeamFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

MARKER = "tenant-a-secret"

# Routes with no tenant-owned object behind them, each with the reason it is safe.
EXEMPT = {
    "api/v1/": "DRF router index: lists route URLs only",
    "api/v1/events/": "routing-key authenticated; covered by the Events API tests",
    "api/v1/auth/csrf/": "sets a cookie, touches no data",
    "api/v1/auth/login/": "credentials endpoint",
    "api/v1/auth/logout/": "ends the caller's own session",
    "api/v1/me/": "the caller's own profile; mass-assignment is tested in the accounts tests",
    "api/v1/auth/mfa/": "second sign-in step; acts only on the caller's own pending session",
    "api/v1/auth/password-reset/": "always 204; tested for enumeration in security tests",
    "api/v1/auth/password-reset/confirm/": "token-authenticated; tested in security tests",
    "api/v1/csp-report/": "accepts browser reports, stores nothing",
}

SKIP_METHODS = {"options", "head", "trace"}
# POSTs that act only on the caller's own account, so succeeding is correct; the snapshot check
# below still proves they changed nothing of anyone else's.
SELF_SCOPED_POSTS = ("read-all/", "me/mfa/setup/", "me/sessions/revoke-others/")


@dataclass(frozen=True)
class Route:
    template: str  # e.g. api/v1/services/{pk}/rotate-key/
    methods: tuple[str, ...]

    @property
    def has_object(self) -> bool:
        return "{" in self.template


def _template(pattern: str) -> str:
    """Normalise both regex (DRF router) and path() routes to `a/{name}/b/`."""
    text = re.sub(r"\(\?P<(\w+)>[^)]*\)", r"{\1}", pattern)
    text = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", text)
    return text.replace("^", "").replace("$", "").replace("\\.", ".")


def enumerate_routes() -> list[Route]:
    found: dict[str, set[str]] = {}

    def walk(patterns, prefix: str = "") -> None:
        for p in patterns:
            if isinstance(p, URLResolver):
                walk(p.url_patterns, prefix + str(p.pattern))
            elif isinstance(p, URLPattern):
                full = prefix + str(p.pattern)
                if not full.startswith("api/v1/") and "api/v1/" not in full:
                    continue
                if "format" in full:
                    continue  # DRF's optional ".json" suffix duplicates (regex and path() forms)
                template = _template(full)
                callback = p.callback
                actions = getattr(callback, "actions", None)
                if actions:
                    methods = set(actions)
                else:
                    cls = getattr(callback, "view_class", None) or getattr(callback, "cls", None)
                    methods = {m for m in getattr(cls, "http_method_names", []) if hasattr(cls, m)}
                found.setdefault(template, set()).update(methods - SKIP_METHODS)

    walk(get_resolver().url_patterns)
    return [Route(t, tuple(sorted(m))) for t, m in sorted(found.items()) if m]


ROUTES = enumerate_routes()


@pytest.fixture
def world():
    team_a, team_b = TeamFactory(name="Tenant-A-Secret team"), TeamFactory(name="Team B")
    user_a = UserFactory(name="Tenant-A-Secret person")
    MembershipFactory(user=user_a, team=team_a, role=Membership.Role.ADMIN)
    user_b = UserFactory()
    MembershipFactory(user=user_b, team=team_b, role=Membership.Role.ADMIN)

    service_a = ServiceFactory(
        team=team_a, name=f"{MARKER}-service", escalation_policy__name=f"{MARKER}-policy"
    )
    schedule_a = ScheduleFactory(team=team_a, name=f"{MARKER}-schedule")
    override_a = ScheduleOverrideFactory(schedule=schedule_a, user=user_a)
    incident_a = IncidentFactory(service=service_a, title=f"{MARKER} incident")
    alert_a = AlertFactory(
        service=service_a, incident=incident_a, summary=f"{MARKER} alert summary"
    )
    note_a = NotificationFactory(incident=incident_a, user=user_a)
    rule_a = NotificationRule.objects.create(user=user_a, channel="email", position=0)
    audit_a = AuditEvent.objects.create(
        action="service.updated", team_id=team_a.pk, actor_email=user_a.email, data={"name": MARKER}
    )
    session_a = SessionRecord.objects.create(session_key="tenant-a-session", user=user_a)
    # Team B has data of its own so "empty" can't be mistaken for "isolated".
    ServiceFactory(team=team_b, name="b-service")

    client = APIClient()
    client.force_authenticate(user_b)
    return {
        "client": client,
        "ids": {
            "team": team_a.pk,
            "user": user_a.pk,
            "service": service_a.pk,
            "policy": service_a.escalation_policy_id,
            "schedule": schedule_a.pk,
            "override": override_a.pk,
            "incident": incident_a.pk,
            "alert": alert_a.pk,
            "notification": note_a.pk,
            "rule": rule_a.pk,
            "audit": audit_a.pk,
            "session": session_a.pk,
        },
        "team_a": team_a,
        "service_a": service_a,
        "incident_a": incident_a,
        "schedule_a": schedule_a,
        "note_a": note_a,
    }


def fill(template: str, ids: dict[str, int]) -> str:
    """Substitute team A's object ids into a route template, by resource."""
    parts = template.split("/")
    resource = parts[2]  # api / v1 / <resource> ...
    values = {
        "teams": {"pk": ids["team"]},
        "users": {"pk": ids["user"]},
        "services": {"pk": ids["service"]},
        "escalation-policies": {"pk": ids["policy"]},
        "schedules": {"pk": ids["schedule"], "schedule_pk": ids["schedule"]},
        "incidents": {"pk": ids["incident"]},
        "notifications": {"pk": ids["notification"]},
        "me": {"pk": ids["session"] if "/sessions/" in template else ids["rule"]},
        "audit-events": {"pk": ids["audit"]},
    }.get(resource)
    if values is None:
        raise AssertionError(f"no cross-team fixture for route {template!r}: classify it")
    path = template
    if "overrides/{pk}" in template:
        path = path.replace("{pk}", str(ids["override"]))
    for name, value in values.items():
        path = path.replace("{" + name + "}", str(value))
    if "{" in path:
        raise AssertionError(f"unfilled placeholder in {template!r} -> {path!r}")
    return "/" + path


def snapshot() -> dict[str, object]:
    return {
        "incidents": list(Incident.objects.values_list("pk", "status", "updated_at")),
        "alerts": Alert.objects.count(),
        "overrides": ScheduleOverride.objects.count(),
        "notifications": list(Notification.objects.values_list("pk", "read_at")),
        "sessions": list(SessionRecord.objects.values_list("pk", flat=True)),
        "audit": AuditEvent.objects.filter(data__name=MARKER).count(),
    }


def test_the_walk_finds_the_whole_api() -> None:
    """Guards the enumerator itself: if it silently found nothing the matrix would be vacuous."""
    templates = {r.template for r in ROUTES}
    assert len(ROUTES) >= 25, sorted(templates)
    for expected in (
        "api/v1/services/",
        "api/v1/services/{pk}/rotate-key/",
        "api/v1/incidents/{pk}/acknowledge/",
        "api/v1/schedules/{schedule_pk}/overrides/{pk}/",
        "api/v1/notifications/read-all/",
        "api/v1/oncalls/",
    ):
        assert expected in templates


def test_every_route_is_classified() -> None:
    """A new endpoint must be added to EXEMPT (with a reason) or get a fixture in `fill`."""
    for route in ROUTES:
        if route.template in EXEMPT:
            continue
        ids = dict.fromkeys(
            (
                "team",
                "user",
                "service",
                "policy",
                "schedule",
                "override",
                "incident",
                "alert",
                "notification",
                "rule",
                "audit",
                "session",
            ),
            1,
        )
        if route.has_object:
            fill(route.template, ids)  # raises for an unknown resource
        else:
            assert route.template.split("/")[2] in {
                "teams",
                "users",
                "services",
                "escalation-policies",
                "schedules",
                "incidents",
                "notifications",
                "me",
                "audit-events",
                "oncalls",
                "analytics",
            }, f"unclassified collection route {route.template!r}"


@pytest.mark.parametrize(
    "route", [r for r in ROUTES if r.template not in EXEMPT], ids=lambda r: r.template
)
def test_another_teams_data_is_unreachable(world, route: Route) -> None:
    client: APIClient = world["client"]
    before = snapshot()

    if route.has_object:
        path = fill(route.template, world["ids"])
        for method in route.methods:
            response = getattr(client, method)(path, data={}, format="json")
            assert response.status_code in (403, 404), (
                f"LEAK: {method.upper()} {path} answered {response.status_code} for another "
                f"team's object: {response.content[:200]!r}"
            )
        assert snapshot() == before, f"{route.template} changed another team's data"
        return

    path = "/" + route.template
    for method in route.methods:
        if method == "get":
            response = client.get(path)
            assert response.status_code == 200, f"GET {path} -> {response.status_code}"
            body = response.content.decode().lower()
            assert MARKER not in body, f"LEAK: GET {path} exposes another team's data"
            assert "tenant a secret" not in body, f"LEAK: GET {path} exposes another team's user"
        elif method == "post":
            payload = {
                "team": world["team_a"].pk,
                "name": "intruder",
                "escalation_policy": world["service_a"].escalation_policy_id,
            }
            response = client.post(path, data=payload, format="json")
            assert response.status_code not in (200, 201, 202, 204) or route.template.endswith(
                SELF_SCOPED_POSTS
            ), f"POST {path} succeeded against another team: {response.content[:200]!r}"
    after = snapshot()
    if route.template.endswith("read-all/"):  # marks only the caller's own rows read
        after["notifications"] = before["notifications"]
    assert after == before, f"{route.template} changed another team's data"


def test_analytics_only_counts_the_callers_teams(world) -> None:
    client: APIClient = world["client"]
    summary = client.get("/api/v1/analytics/summary/").json()
    flat = repr(summary)
    # Team B has no incidents at all; any count of team A's incident would show up here.
    assert Incident.objects.exclude(service__team=world["team_a"]).count() == 0
    numbers = [v for v in _numbers(summary)]
    assert all(n == 0 for n in numbers), f"analytics leaked team A's incident: {flat}"


def _numbers(value):
    if isinstance(value, bool):
        return
    if isinstance(value, int | float):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _numbers(item)
    elif isinstance(value, list):
        for item in value:
            yield from _numbers(item)


def test_notifications_are_private_to_their_owner(world) -> None:
    client: APIClient = world["client"]
    assert client.get("/api/v1/notifications/").json()["results"] == []
    assert client.get("/api/v1/notifications/unread-count/").json()["count"] == 0
    client.post("/api/v1/notifications/read-all/")
    world["note_a"].refresh_from_db()
    assert world["note_a"].read_at is None, "LEAK: another user's inbox was marked read"
