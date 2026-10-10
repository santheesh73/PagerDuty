"""System limits, in one place so product, API docs and enforcement can never disagree.

Exceeding any of these returns HTTP 422 with code `limit_exceeded`.
"""

from typing import Final

from .errors import LimitExceeded

MAX_EVENT_PAYLOAD_BYTES: Final = 512 * 1024
MAX_LEVELS_PER_POLICY: Final = 10
MAX_TARGETS_PER_LEVEL: Final = 5
MAX_LAYERS_PER_SCHEDULE: Final = 5
MAX_MEMBERS_PER_LAYER: Final = 50
MAX_NOTE_LENGTH: Final = 5_000

ALL_LIMITS: Final = {
    "event_payload_bytes": MAX_EVENT_PAYLOAD_BYTES,
    "levels_per_policy": MAX_LEVELS_PER_POLICY,
    "targets_per_level": MAX_TARGETS_PER_LEVEL,
    "layers_per_schedule": MAX_LAYERS_PER_SCHEDULE,
    "members_per_layer": MAX_MEMBERS_PER_LAYER,
    "note_length": MAX_NOTE_LENGTH,
}


def enforce(name: str, value: int) -> None:
    """Raise LimitExceeded if `value` is over the named limit."""
    limit = ALL_LIMITS[name]
    if value > limit:
        raise LimitExceeded(
            f"{name.replace('_', ' ')} is {value}; the limit is {limit}.",
            details={"limit": name, "max": limit, "actual": value},
        )
