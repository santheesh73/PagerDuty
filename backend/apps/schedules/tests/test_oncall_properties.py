"""Property-based tests for the on-call resolver (I2, I3, I11 in docs/INVARIANTS.md).

The example tests in test_oncall.py cover the cases someone thought of. These generate
schedules instead: random layers, rotations, members, overrides and windows, in time zones
chosen for being awkward (30-minute DST shifts, 45-minute offsets, half-hour offsets), with
instants and handoff times pulled towards DST transitions so the hard cases come up often.

`oncall.py` is pure, so none of this touches the database.
Profiles (see conftest): local runs are fast and random; CI is derandomized (fixed seed)
with a higher example count.
"""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from functools import cache
from itertools import pairwise
from zoneinfo import ZoneInfo

from hypothesis import given, settings
from hypothesis import strategies as st

from apps.schedules.models import Rotation
from apps.schedules.oncall import (
    OVERRIDE_SOURCE,
    LayerSpec,
    OverrideSpec,
    ScheduleSpec,
    layer_user_at,
    on_call,
    on_call_with_source,
    render_shifts,
)

# CI scales every property up; local runs stay quick.
SCALE = 2 if os.environ.get("HYPOTHESIS_PROFILE") == "ci" else 1


def examples(n: int) -> settings:
    return settings(max_examples=n * SCALE)


# Awkward zones first: Hypothesis shrinks towards the start of the list.
ZONES = [
    "America/New_York",  # the classic: 1h spring-forward gap, 1h fall-back fold
    "Europe/London",  # transitions at 01:00 local
    "Australia/Lord_Howe",  # DST shift of only 30 minutes
    "Pacific/Chatham",  # +12:45 / +13:45
    "Asia/Kolkata",  # +05:30, no DST
    "UTC",
]
RANGE_START = datetime(2025, 1, 1, tzinfo=UTC)
RANGE_END = datetime(2027, 12, 31, tzinfo=UTC)  # three years: every zone's DST twice+
# The transition table runs past RANGE_END: rotations started late in the range span months.
TABLE_END = datetime(2029, 12, 31, tzinfo=UTC)
SECOND = timedelta(seconds=1)


@cache
def transitions(zone: str) -> tuple[datetime, ...]:
    """Every UTC-offset change for `zone` in the test range, to the second."""
    tz = ZoneInfo(zone)
    found = []
    step = timedelta(hours=1)
    prev_t, prev_off = RANGE_START, RANGE_START.astimezone(tz).utcoffset()
    t = RANGE_START + step
    while t <= TABLE_END:
        off = t.astimezone(tz).utcoffset()
        if off != prev_off:
            lo, hi = prev_t, t  # offset changes somewhere in (lo, hi]
            while hi - lo > SECOND:
                mid = lo + (hi - lo) / 2
                if mid.astimezone(tz).utcoffset() == prev_off:
                    lo = mid
                else:
                    hi = mid
            found.append(hi.replace(microsecond=0))
        prev_t, prev_off = t, off
        t += step
    return tuple(found)


def instants(zone: str) -> st.SearchStrategy[datetime]:
    """Uniform over three years, or within a few hours of one of the zone's DST transitions."""
    seconds = int((RANGE_END - RANGE_START).total_seconds())
    uniform = st.integers(0, seconds).map(lambda s: RANGE_START + timedelta(seconds=s))
    nearby = tuple(t for t in transitions(zone) if t <= RANGE_END)
    if not nearby:
        return uniform
    near = st.tuples(st.sampled_from(nearby), st.integers(-6 * 3600, 6 * 3600)).map(
        lambda pair: pair[0] + timedelta(seconds=pair[1])
    )
    return st.one_of(near, uniform)


# Handoff times that sit on or around DST wall-clock transitions, plus anything else.
AWKWARD_HANDOFFS = [
    time(1, 30),
    time(2, 0),
    time(2, 30),
    time(1, 0),
    time(0, 0),
    time(1, 45),
    time(3, 0),
    time(2, 15),
    time(23, 59),
    time(9, 0),
]
handoffs = st.one_of(
    st.sampled_from(AWKWARD_HANDOFFS),
    st.builds(time, st.integers(0, 23), st.sampled_from([0, 15, 30, 45]), st.just(0)),
    st.builds(time, st.integers(0, 23), st.integers(0, 59), st.integers(0, 59)),
)
user_ids = st.integers(1, 40)


@st.composite
def layer_specs(
    draw: st.DrawFn,
    zone: str,
    priority: int,
    *,
    rotation: str | None = None,
    min_members: int = 1,
) -> LayerSpec:
    rotation = rotation or draw(st.sampled_from([Rotation.DAILY, Rotation.WEEKLY, Rotation.CUSTOM]))
    return LayerSpec(
        name=f"layer-{priority}",
        priority=priority,
        rotation_type=rotation,
        turn_count=draw(st.integers(1, 4)),
        turn_length=(
            timedelta(hours=draw(st.integers(1, 72))) if rotation == Rotation.CUSTOM else None
        ),
        start=draw(instants(zone)),
        handoff_time=draw(handoffs),
        timezone=zone,
        members=tuple(draw(st.lists(user_ids, min_size=min_members, max_size=6, unique=True))),
    )


@st.composite
def override_specs(draw: st.DrawFn, zone: str, seq: int) -> OverrideSpec:
    start = draw(instants(zone))
    length = timedelta(minutes=draw(st.integers(1, 3 * 24 * 60)))
    return OverrideSpec(user_id=draw(user_ids), start=start, end=start + length, seq=seq)


@st.composite
def schedules(draw: st.DrawFn, *, max_overrides: int = 3) -> ScheduleSpec:
    zone = draw(st.sampled_from(ZONES))
    n_layers = draw(st.integers(0, 3))
    priorities = draw(st.permutations(range(10)))[:n_layers]
    layers = tuple(draw(layer_specs(zone, p)) for p in priorities)
    n_overrides = draw(st.integers(0, max_overrides))
    overrides = tuple(draw(override_specs(zone, seq)) for seq in range(1, n_overrides + 1))
    return ScheduleSpec(layers=layers, overrides=overrides)


def zone_of(schedule: ScheduleSpec) -> str:
    return schedule.layers[0].timezone if schedule.layers else "UTC"


@st.composite
def schedule_and_instant(draw: st.DrawFn) -> tuple[ScheduleSpec, datetime]:
    schedule = draw(schedules())
    return schedule, draw(instants(zone_of(schedule)))


@st.composite
def schedule_and_window(draw: st.DrawFn) -> tuple[ScheduleSpec, datetime, datetime]:
    schedule = draw(schedules())
    since = draw(instants(zone_of(schedule)))
    length = timedelta(seconds=draw(st.integers(60, 10 * 24 * 3600)))
    return schedule, since, since + length


def expected_on_call(schedule: ScheduleSpec, at: datetime) -> int | None:
    """The specification, written independently: covering override with the highest seq,
    else the highest-priority layer that has someone, else nobody."""
    covering = [o for o in schedule.overrides if o.start <= at < o.end]
    if covering:
        return max(covering, key=lambda o: o.seq).user_id
    for layer in sorted(schedule.layers, key=lambda layer: -layer.priority):
        user = layer_user_at(layer, at)
        if user is not None:
            return user
    return None


# --- I2: one member or nobody, deterministic, order-independent ------------------------


@examples(400)
@given(schedule_and_instant())
def test_on_call_is_a_member_or_nobody(case: tuple[ScheduleSpec, datetime]) -> None:
    schedule, at = case
    user, source = on_call_with_source(schedule, at)
    if user is None:
        assert source is None
        return
    if source == OVERRIDE_SOURCE:
        assert user in {o.user_id for o in schedule.overrides if o.start <= at < o.end}
    else:
        layer = next(layer for layer in schedule.layers if layer.name == source)
        assert user in layer.members
        assert layer_user_at(layer, at) == user


@examples(300)
@given(schedule_and_instant())
def test_on_call_is_deterministic_and_independent_of_input_order(
    case: tuple[ScheduleSpec, datetime],
) -> None:
    schedule, at = case
    reordered = ScheduleSpec(layers=schedule.layers[::-1], overrides=schedule.overrides[::-1])
    first = on_call_with_source(schedule, at)
    assert on_call_with_source(schedule, at) == first
    assert on_call_with_source(reordered, at) == first


@examples(400)
@given(schedule_and_instant())
def test_overrides_and_layer_priority_follow_the_specification(
    case: tuple[ScheduleSpec, datetime],
) -> None:
    schedule, at = case
    assert on_call(schedule, at) == expected_on_call(schedule, at)


@examples(300)
@given(schedules(), st.data())
def test_a_covering_override_always_wins(schedule: ScheduleSpec, data: st.DataObject) -> None:
    zone = zone_of(schedule)
    at = data.draw(instants(zone))
    winner = OverrideSpec(
        user_id=data.draw(user_ids),
        start=at - timedelta(minutes=data.draw(st.integers(0, 600))),
        end=at + timedelta(minutes=data.draw(st.integers(1, 600))),
        seq=len(schedule.overrides) + 1,
    )
    with_override = ScheduleSpec(layers=schedule.layers, overrides=(*schedule.overrides, winner))
    assert on_call_with_source(with_override, at) == (winner.user_id, OVERRIDE_SOURCE)


# --- I3: render_shifts is a partition that agrees with on_call ---------------------------


def transition_probes(zone: str, since: datetime, until: datetime) -> set[datetime]:
    """Instants every 5 minutes for 90 minutes either side of each DST transition in the
    window: where wall-clock time jumps or repeats, uniform sampling almost never looks."""
    probes = set()
    for transition in transitions(zone):
        if since - timedelta(hours=2) <= transition <= until + timedelta(hours=2):
            probes |= {transition + timedelta(minutes=5 * j) for j in range(-18, 19)}
            probes |= {transition - SECOND, transition}
    return probes


def owner_in(shifts: list, at: datetime) -> int | None:
    containing = [s for s in shifts if s.start <= at < s.end]
    assert len(containing) <= 1, f"{at} is inside {len(containing)} shifts"
    return containing[0].user_id if containing else None


@examples(400)
@given(schedule_and_window(), st.data())
def test_render_shifts_is_a_partition_that_agrees_with_on_call(
    case: tuple[ScheduleSpec, datetime, datetime], data: st.DataObject
) -> None:
    schedule, since, until = case
    shifts = render_shifts(schedule, since, until)

    for shift in shifts:
        assert since <= shift.start < shift.end <= until
    for a, b in pairwise(shifts):
        assert a.end <= b.start, "shifts overlap or are out of order"
        if a.end == b.start:
            assert (a.user_id, a.source) != (b.user_id, b.source), "equal neighbours not merged"

    # Agreement at every edge and midpoint, and at random instants across the window.
    probes = {since, until - SECOND}
    for shift in shifts:
        probes |= {shift.start, shift.end - SECOND, shift.start + (shift.end - shift.start) / 2}
        if shift.start > since:
            probes.add(shift.start - SECOND)
    span = int((until - since).total_seconds())
    probes |= {
        since + timedelta(seconds=s)
        for s in data.draw(st.lists(st.integers(0, max(0, span - 1)), min_size=10, max_size=10))
    }
    probes |= transition_probes(zone_of(schedule), since, until)
    for at in sorted(p for p in probes if since <= p < until):
        assert on_call(schedule, at) == owner_in(shifts, at), f"disagreement at {at.isoformat()}"


@examples(300)
@given(schedule_and_window(), st.data())
def test_on_call_only_changes_at_shift_boundaries(
    case: tuple[ScheduleSpec, datetime, datetime], data: st.DataObject
) -> None:
    """Stability: one second later gives the same answer unless a rendered boundary lies
    between the two instants."""
    schedule, since, until = case
    shifts = render_shifts(schedule, since, until)
    boundaries = {s.start for s in shifts} | {s.end for s in shifts}
    span = int((until - since).total_seconds())
    if span < 2:
        return
    for offset in data.draw(st.lists(st.integers(0, span - 2), min_size=1, max_size=20)):
        at = since + timedelta(seconds=offset)
        if at + SECOND not in boundaries:
            assert on_call(schedule, at) == on_call(schedule, at + SECOND), at.isoformat()


# --- Rotation fairness -------------------------------------------------------------------


@st.composite
def single_rotating_layer(draw: st.DrawFn) -> LayerSpec:
    zone = draw(st.sampled_from(ZONES))
    return draw(layer_specs(zone, 0, min_members=1))


def first_instant(day: date, handoff: time, zone: str) -> datetime:
    """Oracle for "when does shift day `day` begin": the first instant whose local wall time
    reaches `day handoff`. Independent of oncall.py: a gap is resolved from the
    precomputed transition table, not by searching."""
    tz = ZoneInfo(zone)
    wall = datetime.combine(day, handoff)
    first = wall.replace(tzinfo=tz, fold=0).astimezone(UTC)
    if first.astimezone(tz).replace(tzinfo=None) == wall:
        return first  # exists; fold=0 is the first occurrence of a repeated time
    before_gap = wall.replace(tzinfo=tz, fold=1).astimezone(UTC)
    return next(t for t in transitions(zone) if before_gap <= t <= first)


def turn_sample_instants(layer: LayerSpec, turns: int) -> list[datetime]:
    """One instant inside each of the first `turns` turns, computed from the spec directly."""
    if layer.rotation_type == Rotation.CUSTOM:
        assert layer.turn_length
        return [layer.start + layer.turn_length * k + layer.turn_length / 2 for k in range(turns)]
    tz = ZoneInfo(layer.timezone)
    local = layer.start.astimezone(tz).date()
    day0 = next(
        d
        for d in (local + timedelta(days=1), local, local - timedelta(days=1))
        if first_instant(d, layer.handoff_time, layer.timezone) <= layer.start
    )
    days = layer.turn_count * (7 if layer.rotation_type == Rotation.WEEKLY else 1)
    samples = []
    for k in range(turns):
        turn_start = first_instant(
            day0 + timedelta(days=k * days), layer.handoff_time, layer.timezone
        )
        next_start = first_instant(
            day0 + timedelta(days=(k + 1) * days), layer.handoff_time, layer.timezone
        )
        lower = max(turn_start, layer.start)
        samples.append(lower + (next_start - lower) / 2)  # middle of the turn
    return samples


@examples(300)
@given(single_rotating_layer())
def test_rotation_is_round_robin_over_n_turns(layer: LayerSpec) -> None:
    n = len(layer.members)
    owners = [layer_user_at(layer, at) for at in turn_sample_instants(layer, 2 * n)]
    assert owners == [layer.members[k % n] for k in range(2 * n)]
    assert set(owners[:n]) == set(layer.members), "someone never got a turn"
    if n > 1:
        assert all(a != b for a, b in pairwise(owners)), "back-to-back turns"


# --- I11: local handoff time survives DST ---------------------------------------------------


@st.composite
def dst_window(draw: st.DrawFn) -> tuple[LayerSpec, datetime, datetime]:
    """A daily or weekly layer and a window straddling one of its zone's DST transitions."""
    zone = draw(st.sampled_from([z for z in ZONES if transitions(z)]))
    rotation = draw(st.sampled_from([Rotation.DAILY, Rotation.WEEKLY]))
    layer = draw(layer_specs(zone, 0, rotation=rotation, min_members=2))
    transition = draw(st.sampled_from(transitions(zone)))
    # Start the layer well before the window so every boundary inside it is a handoff.
    layer = replace(layer, start=transition - timedelta(days=60))
    span_days = layer.turn_count * (7 if rotation == Rotation.WEEKLY else 1) * 2 + 2
    since = transition - timedelta(days=span_days)
    return layer, since, transition + timedelta(days=span_days)


@examples(300)
@given(dst_window())
def test_daily_and_weekly_handoffs_land_on_the_local_handoff_time_across_dst(
    case: tuple[LayerSpec, datetime, datetime],
) -> None:
    layer, since, until = case
    tz = ZoneInfo(layer.timezone)
    schedule = ScheduleSpec(layers=(layer,))
    shifts = render_shifts(schedule, since, until)
    # The layer must agree with its own rendering on both sides of the transition.
    for at in sorted(
        p for p in transition_probes(layer.timezone, since, until) if since <= p < until
    ):
        assert on_call(schedule, at) == owner_in(shifts, at), f"disagreement at {at.isoformat()}"
    for boundary in (s.start for s in shifts if s.start > since):
        local = boundary.astimezone(tz)
        if local.time() == layer.handoff_time:
            # On a repeated (fall-back) hour the handoff is the first occurrence.
            assert local.fold == 0, f"handoff at the second {local.time()} on {local.date()}"
            continue
        # Otherwise the handoff wall time must not exist that day (spring-forward gap) and
        # the boundary is the first instant after the gap.
        wall = datetime.combine(local.date(), layer.handoff_time)
        round_trip = wall.replace(tzinfo=tz).astimezone(UTC).astimezone(tz).replace(tzinfo=None)
        assert round_trip != wall, (
            f"handoff at {local.isoformat()} but {layer.handoff_time} exists on {local.date()}"
        )
        before = (boundary - SECOND).astimezone(tz)
        assert before.utcoffset() != local.utcoffset(), "boundary is not at the end of the gap"
