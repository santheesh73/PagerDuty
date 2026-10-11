"""I1's structural guard, tested on its own.

Ingest also takes a per-dedup-key advisory lock, which serialises the concurrent-trigger race test by
itself. So without this test the partial unique index (the guarantee the docs describe) could be
dropped and nothing would fail. The mutation `dedup-index` proves this test notices.
"""

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.catalog.models import Service
from apps.incidents.models import Incident, Status
from tests.factories import IncidentFactory

pytestmark = pytest.mark.django_db


def test_the_database_refuses_a_second_open_incident_for_one_dedup_key(service: Service) -> None:
    first = IncidentFactory(service=service, dedup_key="db-1/disk")
    with pytest.raises(IntegrityError), transaction.atomic():
        IncidentFactory(service=service, dedup_key="db-1/disk", status=Status.ACKNOWLEDGED)

    # Resolving frees the key, and the same key on another service never conflicts.
    Incident.objects.filter(pk=first.pk).update(status=Status.RESOLVED, resolved_at=timezone.now())
    IncidentFactory(service=service, dedup_key="db-1/disk")
    IncidentFactory(dedup_key="db-1/disk")
    assert Incident.objects.filter(dedup_key="db-1/disk").count() == 3
