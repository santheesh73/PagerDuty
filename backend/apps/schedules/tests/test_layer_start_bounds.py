"""A layer that starts in year 1 made `/oncall/` raise OverflowError (a 500) and would have made
Events ingest fail for every service on that schedule, losing the alert."""

from datetime import UTC, datetime, time

import pytest
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from apps.catalog.models import Service
from apps.schedules.models import Rotation, ScheduleLayer
from apps.schedules.oncall import LayerSpec, ScheduleSpec, on_call
from conftest import Paging
from tests.factories import ScheduleFactory

pytestmark = pytest.mark.django_db
URL = "/api/v1/schedules/"


def body(service: Service, people: Paging, start: str) -> dict:
    return {
        "team": service.team_id,
        "name": "bounds",
        "timezone": "UTC",
        "layers": [
            {
                "name": "P",
                "rotation_type": "daily",
                "turn_count": 1,
                "start": start,
                "handoff_time": "09:00:00",
                "members": [people.on_call.pk, people.off_call.pk],
            }
        ],
    }


@pytest.mark.parametrize(
    "start", ["0001-01-01T00:00:00Z", "1969-12-31T23:59:59Z", "9999-12-31T00:00:00Z"]
)
def test_the_api_rejects_a_layer_start_outside_a_sane_range(
    api_client: APIClient, service: Service, people: Paging, start: str
) -> None:
    api_client.force_login(people.admin)
    response = api_client.post(URL, body(service, people, start), format="json")
    assert response.status_code == 422, response.content


def test_the_api_accepts_an_ordinary_start(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    api_client.force_login(people.admin)
    response = api_client.post(URL, body(service, people, "2026-01-05T09:00:00Z"), format="json")
    assert response.status_code == 201, response.content


def test_the_database_refuses_an_out_of_range_start() -> None:
    schedule = ScheduleFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        ScheduleLayer.objects.create(
            schedule=schedule,
            name="bad",
            rotation_type=Rotation.DAILY,
            start=datetime(1, 1, 1, tzinfo=UTC),
            handoff_time=time(9, 0),
        )


def test_the_resolver_skips_a_layer_it_cannot_evaluate_instead_of_raising() -> None:
    broken = LayerSpec(
        name="broken",
        priority=2,
        rotation_type="daily",
        turn_count=1,
        turn_length=None,
        start=datetime(1, 1, 1, tzinfo=UTC),
        handoff_time=time(9, 0),
        timezone="UTC",
        members=(1, 2),
    )
    healthy = LayerSpec(
        name="healthy",
        priority=1,
        rotation_type="daily",
        turn_count=1,
        turn_length=None,
        start=datetime(2026, 1, 5, tzinfo=UTC),
        handoff_time=time(9, 0),
        timezone="UTC",
        members=(7,),
    )
    schedule = ScheduleSpec(layers=(broken, healthy))
    # The broken layer outranks the healthy one, but must not take paging down with it.
    assert on_call(schedule, datetime(2026, 3, 1, 12, tzinfo=UTC)) == 7
