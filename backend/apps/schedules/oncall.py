"""Who is on call, as pure functions over plain data.

No ORM access here: callers load a `ScheduleSpec` (see selectors.load_schedule_spec) and
these functions answer questions about it. That keeps the rotation maths fast to test
exhaustively — DST transitions included — and lets the API, the shift timeline and the
escalation engine share exactly one implementation.

Rotation model
--------------
* daily / weekly: turns are counted in *local calendar days* in the schedule's timezone.
  A "shift day" starts at `handoff_time` local, so a 09:00 handoff stays 09:00 through DST
  (the shift on a DST day is simply 23 or 25 hours long).
* custom: turns are fixed absolute durations (e.g. 12h) measured from `start`; they ignore
  wall-clock time by design, so their local handoff drifts by an hour across DST.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo

from .models import Rotation

OVERRIDE_SOURCE = "override"


@dataclass(frozen=True, slots=True)
class LayerSpec:
    name: str
    priority: int
    rotation_type: str
    turn_count: int
    turn_length: timedelta | None
    start: datetime
    handoff_time: time
    timezone: str
    members: tuple[int, ...]  # user ids in rotation order


@dataclass(frozen=True, slots=True)
class OverrideSpec:
    user_id: int
    start: datetime
    end: datetime  # exclusive
    seq: int  # creation order: the latest override wins when several overlap


@dataclass(frozen=True, slots=True)
class ScheduleSpec:
    layers: tuple[LayerSpec, ...]
    overrides: tuple[OverrideSpec, ...] = ()


@dataclass(frozen=True, slots=True)
class Shift:
    user_id: int
    start: datetime
    end: datetime
    source: str  # layer name, or "override"


# --- single layer -------------------------------------------------------------------------


def layer_user_at(layer: LayerSpec, at: datetime) -> int | None:
    if not layer.members or at < layer.start:
        return None
    if layer.rotation_type == Rotation.CUSTOM:
        turns = (at - layer.start) // _turn_length(layer)
    else:
        tz = ZoneInfo(layer.timezone)
        day = _shift_day(at.astimezone(tz), layer.handoff_time)
        day0 = _shift_day(layer.start.astimezone(tz), layer.handoff_time)
        turns = (day - day0).days // _days_per_turn(layer)
    return layer.members[turns % len(layer.members)]


def _shift_day(local: datetime, handoff: time) -> date:
    """The calendar date whose shift `local` falls in: before the handoff, it's yesterday's."""
    return local.date() if local.time() >= handoff else local.date() - timedelta(days=1)


def _turn_length(layer: LayerSpec) -> timedelta:
    # A DB check constraint guarantees custom layers have a turn_length.
    if not layer.turn_length or layer.turn_length <= timedelta(0):
        raise ValueError(f"custom layer {layer.name!r} needs a positive turn_length")
    return layer.turn_length


def _days_per_turn(layer: LayerSpec) -> int:
    return layer.turn_count * (7 if layer.rotation_type == Rotation.WEEKLY else 1)


# --- whole schedule -----------------------------------------------------------------------


def on_call(schedule: ScheduleSpec, at: datetime) -> int | None:
    user_id, _ = on_call_with_source(schedule, at)
    return user_id


def on_call_with_source(schedule: ScheduleSpec, at: datetime) -> tuple[int | None, str | None]:
    """Override covering `at` (latest wins) → highest-priority layer with a user → nobody."""
    covering = [o for o in schedule.overrides if o.start <= at < o.end]
    if covering:
        return max(covering, key=lambda o: o.seq).user_id, OVERRIDE_SOURCE
    for layer in sorted(schedule.layers, key=lambda lay: lay.priority, reverse=True):
        user_id = layer_user_at(layer, at)
        if user_id is not None:
            return user_id, layer.name
    return None, None


def render_shifts(schedule: ScheduleSpec, since: datetime, until: datetime) -> list[Shift]:
    """The on-call timeline for [since, until), as merged contiguous shifts.

    Every instant where the answer *could* change is a boundary (layer handoffs, layer
    starts, override edges). Between two boundaries nothing changes, so evaluating
    `on_call` once per segment is exact.
    """
    if until <= since:
        return []
    points = {since, until}
    for layer in schedule.layers:
        points.update(_layer_boundaries(layer, since, until))
    for override in schedule.overrides:
        points.update(p for p in (override.start, override.end) if since < p < until)
    ordered = sorted(points)

    shifts: list[Shift] = []
    for start, end in pairwise(ordered):
        user_id, source = on_call_with_source(schedule, start)
        if user_id is None or source is None:
            continue
        last = shifts[-1] if shifts else None
        if last and last.end == start and last.user_id == user_id and last.source == source:
            shifts[-1] = Shift(user_id, last.start, end, source)
        else:
            shifts.append(Shift(user_id, start, end, source))
    return shifts


def _layer_boundaries(layer: LayerSpec, since: datetime, until: datetime) -> Iterator[datetime]:
    if since < layer.start < until:
        yield layer.start
    if not layer.members:
        return
    lower = max(since, layer.start)
    if layer.rotation_type == Rotation.CUSTOM:
        length = _turn_length(layer)
        point = layer.start + max(0, (lower - layer.start) // length) * length
        while point < until:
            if point > since:
                yield point
            point += length
        return

    tz = ZoneInfo(layer.timezone)
    day0 = _shift_day(layer.start.astimezone(tz), layer.handoff_time)
    step = _days_per_turn(layer)
    day = _shift_day(lower.astimezone(tz), layer.handoff_time)
    day -= timedelta(days=(day - day0).days % step)  # back up to this turn's first day
    while True:
        point = _first_instant_of_shift_day(day, layer.handoff_time, tz)
        if point >= until:
            return
        if point > since:
            yield point
        day += timedelta(days=step)


def _first_instant_of_shift_day(day: date, handoff: time, tz: ZoneInfo) -> datetime:
    """The earliest UTC instant whose local time on `day` is >= `handoff`.

    Normally that's simply `day handoff` local. Two DST cases need care:
    * ambiguous wall time (fall back): fold=0 picks the first occurrence — correct.
    * non-existent wall time (spring forward gap, e.g. 02:30 in New York): the clock jumps
      past the handoff, so the shift starts at the end of the gap. Binary-search for it.
    """
    wall = datetime.combine(day, handoff)
    candidate = wall.replace(tzinfo=tz).astimezone(UTC)
    if candidate.astimezone(tz).replace(tzinfo=None) == wall:
        return candidate
    lo = wall.replace(tzinfo=tz, fold=1).astimezone(UTC)  # maps to before the gap
    hi = candidate  # maps to after the gap
    while hi - lo > timedelta(seconds=1):
        mid = lo + (hi - lo) / 2
        if _shift_day(mid.astimezone(tz), handoff) == day:
            hi = mid
        else:
            lo = mid
    return hi.replace(microsecond=0)
