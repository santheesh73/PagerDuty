"""Maintenance and debug suppress paging, so the window must always be bounded."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import Service
from conftest import Paging

pytestmark = pytest.mark.django_db


def _set_mode(client: APIClient, service: Service, **payload: object):
    return client.post(f"/api/v1/services/{service.pk}/mode/", payload, format="json")


@pytest.mark.parametrize("mode", [Service.Mode.MAINTENANCE, Service.Mode.DEBUG])
def test_open_ended_window_is_rejected(
    api_client: APIClient, service: Service, people: Paging, mode: str
) -> None:
    api_client.force_login(people.admin)
    response = _set_mode(api_client, service, mode=mode)
    assert response.status_code == 422, "a service could be silenced for good"
    service.refresh_from_db()
    assert service.mode == Service.Mode.ACTIVE


def test_window_beyond_the_limit_is_rejected(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    api_client.force_login(people.admin)
    until = timezone.now() + timedelta(days=30)
    response = _set_mode(
        api_client, service, mode=Service.Mode.MAINTENANCE, until=until.isoformat()
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "limit_exceeded"


def test_bounded_window_is_accepted(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    api_client.force_login(people.admin)
    until = timezone.now() + timedelta(hours=2)
    response = _set_mode(
        api_client, service, mode=Service.Mode.MAINTENANCE, until=until.isoformat()
    )
    assert response.status_code == 200
    service.refresh_from_db()
    assert service.mode == Service.Mode.MAINTENANCE
    assert service.mode_until is not None


def test_returning_to_active_needs_no_window(
    api_client: APIClient, service: Service, people: Paging
) -> None:
    api_client.force_login(people.admin)
    assert _set_mode(api_client, service, mode=Service.Mode.ACTIVE).status_code == 200
