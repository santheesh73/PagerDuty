from typing import Any

from apps.accounts.models import User

from .models import EventType, Incident, IncidentEvent


def record(
    incident: Incident,
    type: EventType,
    *,
    actor: User | None = None,
    message: str = "",
    **data: Any,
) -> IncidentEvent:
    """Append one entry to the incident's timeline. `actor=None` means the system acted."""
    return IncidentEvent.objects.create(
        incident=incident, type=type, actor=actor, message=message, data=data
    )
