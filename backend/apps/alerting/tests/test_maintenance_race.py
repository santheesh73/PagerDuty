"""An alert that arrives as maintenance ends is judged by the mode in force, not a stale copy.

`ingest` used to read `service.mode` from the object it was handed, before taking any lock. If a
window had just ended (the expiry sweep resolves the maintenance incident and switches the mode
back), the waiting alert still believed the service was in maintenance, opened a *new*
maintenance incident on an active service, and never paged (found by the final audit).
"""

import pytest

from apps.alerting.actions import Event, ingest
from apps.catalog.actions import set_mode
from apps.catalog.models import Service
from apps.incidents.models import Incident
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


def test_an_alert_holding_a_stale_maintenance_service_still_pages(service: Service) -> None:
    set_mode(service, Service.Mode.MAINTENANCE)
    stale = Service.objects.get(pk=service.pk)  # what the request read before the window ended
    assert stale.mode == Service.Mode.MAINTENANCE

    set_mode(Service.objects.get(pk=service.pk), Service.Mode.ACTIVE)  # the window ends

    result = ingest(stale, Event(action="trigger", dedup_key="after-window", summary="disk full"))

    incident = Incident.objects.get(pk=result.incident_id)
    assert not incident.is_maintenance
    assert Notification.objects.filter(incident=incident).exists(), "someone is paged"


def test_an_alert_during_maintenance_is_still_suppressed(service: Service) -> None:
    set_mode(service, Service.Mode.MAINTENANCE)
    result = ingest(
        Service.objects.get(pk=service.pk),
        Event(action="trigger", dedup_key="during", summary="noise"),
    )
    incident = Incident.objects.get(pk=result.incident_id)
    assert incident.is_maintenance
    assert not Notification.objects.filter(incident=incident).exists()
