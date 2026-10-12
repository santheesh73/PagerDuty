"""The incident list is polled by the SPA; its order must be served by an index, not a sort."""

import pytest
from django.db import connection

pytestmark = pytest.mark.django_db


def test_the_incident_list_order_has_an_index() -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'incident_list_order_idx'"
        )
        row = cursor.fetchone()
    assert row is not None, "migration incidents/0002 builds it concurrently"
    assert "triggered_at DESC" in row[0]
    assert "id DESC" in row[0]
