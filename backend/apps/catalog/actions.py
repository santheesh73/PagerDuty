from datetime import datetime

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.incidents import actions as incident_actions
from apps.incidents.models import Incident, Status

from .models import Service, generate_integration_key


def rotate_integration_key(service: Service) -> Service:
    service.integration_key = generate_integration_key()
    service.save(update_fields=["integration_key", "updated_at"])
    return service


def set_mode(
    service: Service,
    mode: str,
    *,
    until: datetime | None = None,
    actor: User | None = None,
    now: datetime | None = None,
) -> Service:
    """Switch a service's mode. Leaving maintenance resolves its maintenance incident."""
    now = now or timezone.now()
    with transaction.atomic():
        service = Service.objects.select_for_update().get(pk=service.pk)
        leaving_maintenance = (
            service.mode == Service.Mode.MAINTENANCE and mode != Service.Mode.MAINTENANCE
        )
        service.mode = mode
        service.mode_until = until if mode != Service.Mode.ACTIVE else None
        service.save(update_fields=["mode", "mode_until", "updated_at"])
        if leaving_maintenance:
            _end_maintenance(service, actor=actor, now=now)
        return service


def expire_service_modes(*, now: datetime | None = None) -> int:
    """Return every service whose mode window has passed to `active`."""
    now = now or timezone.now()
    expired = Service.objects.filter(mode_until__lte=now).exclude(mode=Service.Mode.ACTIVE)
    count = 0
    for service in expired:
        set_mode(service, Service.Mode.ACTIVE, now=now)
        count += 1
    return count


def _end_maintenance(service: Service, *, actor: User | None, now: datetime) -> None:
    for incident_id in (
        Incident.objects.filter(service=service, is_maintenance=True)
        .exclude(status=Status.RESOLVED)
        .values_list("pk", flat=True)
    ):
        incident_actions.resolve(incident_id, actor=actor, now=now, via="maintenance window")
