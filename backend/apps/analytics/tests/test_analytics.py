from datetime import timedelta

import pytest
from rest_framework.test import APIClient

from apps.catalog import actions as catalog_actions
from apps.catalog.models import Service
from apps.escalations import engine
from apps.incidents import actions
from apps.incidents.models import Incident
from conftest import T0, Paging, TriggerFn
from tests.factories import ServiceFactory

pytestmark = pytest.mark.django_db
MIN = timedelta(minutes=1)
WINDOW = "since=2026-01-01T00:00:00Z&until=2026-01-31T00:00:00Z"


@pytest.fixture
def history(service: Service, people: Paging, trigger: TriggerFn) -> list[Incident]:
    """Three incidents with known response times (minutes):
    #1 ack 2, resolve 10 · #2 escalated at 5, ack 6, resolve 30 · #3 still open."""
    a = trigger(service, "a").incident_id
    actions.acknowledge(a, actor=people.on_call, now=T0 + 2 * MIN)
    actions.resolve(a, actor=people.on_call, now=T0 + 10 * MIN)

    b = trigger(service, "b", now=T0 + timedelta(days=1)).incident_id
    engine.escalate(b, 0, 0, T0 + timedelta(days=1) + 5 * MIN)
    actions.acknowledge(b, actor=people.admin, now=T0 + timedelta(days=1) + 6 * MIN)
    actions.resolve(b, actor=people.admin, now=T0 + timedelta(days=1) + 30 * MIN)

    c = trigger(service, "c", severity="warning", now=T0 + timedelta(days=1)).incident_id
    trigger(service, "c", now=T0 + timedelta(days=1))  # duplicate alert
    return list(Incident.objects.filter(pk__in=[a, b, c]))


def test_summary_metrics(api_client: APIClient, history: list[Incident], people: Paging) -> None:
    api_client.force_login(people.viewer)
    body = api_client.get(f"/api/v1/analytics/summary/?{WINDOW}").json()

    assert body["incidents"] == 3
    assert body["by_urgency"] == {"high": 2, "low": 1}
    assert body["time_to_first_response_seconds"] == 4 * 60  # (2 + 6) / 2
    assert body["mtta_seconds"] == 4 * 60
    assert body["mttr_seconds"] == 20 * 60  # (10 + 30) / 2
    assert body["escalation_rate"] == round(1 / 3, 4)
    assert body["noisy_services"][0]["alerts"] == 4


def test_source_driven_resolves_do_not_count_as_first_response(
    api_client: APIClient, service: Service, people: Paging, trigger: TriggerFn
) -> None:
    trigger(service, "x")
    trigger(service, "x", action="resolve", now=T0 + 3 * MIN)
    api_client.force_login(people.viewer)
    body = api_client.get(f"/api/v1/analytics/summary/?{WINDOW}").json()
    assert body["time_to_first_response_seconds"] is None
    assert body["mttr_seconds"] == 180


def test_maintenance_incidents_are_excluded(
    api_client: APIClient, service: Service, people: Paging, trigger: TriggerFn
) -> None:
    catalog_actions.set_mode(service, Service.Mode.MAINTENANCE, now=T0)
    service.refresh_from_db()
    trigger(service, "quiet")
    api_client.force_login(people.viewer)
    assert api_client.get(f"/api/v1/analytics/summary/?{WINDOW}").json()["incidents"] == 0


def test_summary_is_scoped_to_your_teams_and_filters(
    api_client: APIClient, history: list[Incident], people: Paging, trigger: TriggerFn
) -> None:
    other = ServiceFactory()
    trigger(other, "elsewhere")
    api_client.force_login(people.viewer)
    assert api_client.get(f"/api/v1/analytics/summary/?{WINDOW}").json()["incidents"] == 3
    assert (
        api_client.get(f"/api/v1/analytics/summary/?{WINDOW}&service={other.pk}").json()[
            "incidents"
        ]
        == 0
    )


def test_timeseries_is_zero_filled_by_local_day(
    api_client: APIClient, history: list[Incident], people: Paging
) -> None:
    api_client.force_login(people.viewer)
    points = api_client.get(
        "/api/v1/analytics/timeseries/?since=2026-01-06T00:00:00Z&until=2026-01-10T00:00:00Z&tz=UTC"
    ).json()
    assert [(p["date"], p["incidents"]) for p in points] == [
        ("2026-01-06", 0),
        ("2026-01-07", 1),
        ("2026-01-08", 2),
        ("2026-01-09", 0),
    ]
    assert points[1]["mtta_seconds"] == 120


def test_bad_windows_and_zones_are_rejected(api_client: APIClient, people: Paging) -> None:
    api_client.force_login(people.viewer)
    assert (
        api_client.get(
            "/api/v1/analytics/summary/?since=2027-01-01T00:00:00Z&until=2026-01-01T00:00:00Z"
        ).status_code
        == 422
    )
    assert api_client.get("/api/v1/analytics/timeseries/?tz=Nowhere").status_code == 422
