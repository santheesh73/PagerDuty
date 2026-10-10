"""On-call resolver: pure functions, no database. Times are written in UTC with the local
equivalent alongside so the DST cases can be checked by eye."""

from datetime import UTC, datetime, time, timedelta

from apps.schedules.models import Rotation
from apps.schedules.oncall import (
    LayerSpec,
    OverrideSpec,
    ScheduleSpec,
    Shift,
    layer_user_at,
    on_call,
    render_shifts,
)

ALICE, BOB, CAROL, DAVE = 1, 2, 3, 4


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def layer(
    members: tuple[int, ...] = (ALICE, BOB, CAROL),
    *,
    rotation: Rotation = Rotation.DAILY,
    start: datetime = utc(2026, 1, 5, 9),
    handoff: time = time(9, 0),
    tz: str = "UTC",
    turn_count: int = 1,
    turn_length: timedelta | None = None,
    priority: int = 0,
    name: str = "Primary",
) -> LayerSpec:
    return LayerSpec(
        name=name,
        priority=priority,
        rotation_type=rotation,
        turn_count=turn_count,
        turn_length=turn_length,
        start=start,
        handoff_time=handoff,
        timezone=tz,
        members=members,
    )


def schedule(*layers: LayerSpec, overrides: tuple[OverrideSpec, ...] = ()) -> ScheduleSpec:
    return ScheduleSpec(layers=layers, overrides=overrides)


# --- single layer ----------------------------------------------------------------------


def test_daily_rotation_hands_off_exactly_at_handoff_time() -> None:
    lay = layer()
    assert layer_user_at(lay, utc(2026, 1, 5, 9, 0)) == ALICE
    assert layer_user_at(lay, utc(2026, 1, 6, 8, 59, 59)) == ALICE
    assert layer_user_at(lay, utc(2026, 1, 6, 9, 0)) == BOB
    assert layer_user_at(lay, utc(2026, 1, 7, 9, 0)) == CAROL
    assert layer_user_at(lay, utc(2026, 1, 8, 9, 0)) == ALICE  # wraps around


def test_nobody_is_on_call_before_the_layer_starts() -> None:
    assert layer_user_at(layer(), utc(2026, 1, 5, 8, 59)) is None


def test_empty_layer_has_nobody_on_call() -> None:
    assert layer_user_at(layer(members=()), utc(2026, 2, 1)) is None


def test_layer_starting_before_handoff_time_belongs_to_the_previous_shift_day() -> None:
    # Starts 06:00, hands off at 09:00: Alice has 06:00-09:00, then Bob takes over.
    lay = layer(start=utc(2026, 1, 5, 6))
    assert layer_user_at(lay, utc(2026, 1, 5, 7)) == ALICE
    assert layer_user_at(lay, utc(2026, 1, 5, 9)) == BOB


def test_multi_day_turns() -> None:
    lay = layer(turn_count=3)
    assert layer_user_at(lay, utc(2026, 1, 7, 12)) == ALICE
    assert layer_user_at(lay, utc(2026, 1, 8, 9)) == BOB


def test_weekly_rotation_with_two_week_turns() -> None:
    lay = layer((ALICE, BOB), rotation=Rotation.WEEKLY, turn_count=2)
    assert layer_user_at(lay, utc(2026, 1, 18, 12)) == ALICE  # day 13
    assert layer_user_at(lay, utc(2026, 1, 19, 8, 59)) == ALICE
    assert layer_user_at(lay, utc(2026, 1, 19, 9)) == BOB  # day 14
    assert layer_user_at(lay, utc(2026, 2, 2, 9)) == ALICE  # day 28


def test_custom_rotation_uses_absolute_hours() -> None:
    lay = layer((ALICE, BOB), rotation=Rotation.CUSTOM, turn_length=timedelta(hours=12))
    assert layer_user_at(lay, utc(2026, 1, 5, 20, 59)) == ALICE
    assert layer_user_at(lay, utc(2026, 1, 5, 21)) == BOB
    assert layer_user_at(lay, utc(2026, 1, 6, 9)) == ALICE


# --- DST -------------------------------------------------------------------------------
# America/New_York: 2026-03-08 02:00 EST → 03:00 EDT;  2026-11-01 02:00 EDT → 01:00 EST.
# Europe/London:    2026-03-29 01:00 GMT → 02:00 BST;  2026-10-25 02:00 BST → 01:00 GMT.


def test_dst_spring_forward_keeps_the_local_handoff_time_in_new_york() -> None:
    ny = layer((ALICE, BOB), start=utc(2026, 3, 2, 14), tz="America/New_York")  # 09:00 EST
    # Before DST the 09:00 handoff is 14:00 UTC; after it, 13:00 UTC. Turns count local days.
    assert layer_user_at(ny, utc(2026, 3, 7, 14)) == BOB  # day 6
    assert layer_user_at(ny, utc(2026, 3, 8, 12, 59)) == BOB  # 08:59 EDT, still Mar 7's shift
    assert layer_user_at(ny, utc(2026, 3, 8, 13)) == ALICE  # 09:00 EDT, day 7
    assert layer_user_at(ny, utc(2026, 3, 9, 13)) == BOB  # 09:00 EDT, not 10:00


def test_dst_fall_back_keeps_the_local_handoff_time_in_new_york() -> None:
    ny = layer((ALICE, BOB), start=utc(2026, 10, 26, 13), tz="America/New_York")  # 09:00 EDT
    assert layer_user_at(ny, utc(2026, 10, 31, 13)) == BOB  # Oct 31, 09:00 EDT, day 5
    assert layer_user_at(ny, utc(2026, 11, 1, 13, 59)) == BOB  # 08:59 EST on Nov 1
    assert layer_user_at(ny, utc(2026, 11, 1, 14)) == ALICE  # 09:00 EST, day 6


def test_dst_transitions_in_london() -> None:
    ldn = layer((ALICE, BOB), start=utc(2026, 3, 23, 9), tz="Europe/London")  # 09:00 GMT
    assert layer_user_at(ldn, utc(2026, 3, 29, 7, 59)) == BOB  # 08:59 BST, day 5 (Mar 28)
    assert layer_user_at(ldn, utc(2026, 3, 29, 8)) == ALICE  # 09:00 BST, day 6
    fall = layer((ALICE, BOB), start=utc(2026, 10, 19, 8), tz="Europe/London")  # 09:00 BST
    assert layer_user_at(fall, utc(2026, 10, 25, 8, 59)) == BOB  # 08:59 GMT, day 5 (Oct 24)
    assert layer_user_at(fall, utc(2026, 10, 25, 9)) == ALICE  # 09:00 GMT, day 6


def test_custom_rotation_is_absolute_so_its_local_handoff_moves_across_dst() -> None:
    # 24h custom turns are absolute: after spring-forward the local handoff moves 09:00 → 10:00.
    ny = layer(
        (ALICE, BOB),
        rotation=Rotation.CUSTOM,
        turn_length=timedelta(hours=24),
        start=utc(2026, 3, 7, 14),
        tz="America/New_York",
    )
    assert layer_user_at(ny, utc(2026, 3, 8, 13)) == ALICE  # 09:00 EDT: no handoff yet
    assert layer_user_at(ny, utc(2026, 3, 8, 14)) == BOB  # 10:00 EDT


# --- whole schedule ----------------------------------------------------------------------


def test_override_beats_every_layer() -> None:
    sched = schedule(
        layer(),
        overrides=(
            OverrideSpec(user_id=DAVE, start=utc(2026, 1, 6, 12), end=utc(2026, 1, 6, 18), seq=1),
        ),
    )
    assert on_call(sched, utc(2026, 1, 6, 11, 59)) == BOB
    assert on_call(sched, utc(2026, 1, 6, 12)) == DAVE
    assert on_call(sched, utc(2026, 1, 6, 18)) == BOB  # end is exclusive


def test_latest_created_override_wins_when_overrides_overlap() -> None:
    sched = schedule(
        layer(),
        overrides=(
            OverrideSpec(user_id=DAVE, start=utc(2026, 1, 6), end=utc(2026, 1, 7), seq=1),
            OverrideSpec(user_id=CAROL, start=utc(2026, 1, 6, 10), end=utc(2026, 1, 6, 11), seq=2),
        ),
    )
    assert on_call(sched, utc(2026, 1, 6, 10, 30)) == CAROL
    assert on_call(sched, utc(2026, 1, 6, 11, 30)) == DAVE


def test_highest_priority_layer_with_someone_on_call_wins() -> None:
    primary = layer((ALICE,), priority=1)
    weekend = layer((DAVE,), priority=5, start=utc(2026, 1, 10, 9), name="Weekend")
    sched = schedule(primary, weekend)
    assert on_call(sched, utc(2026, 1, 9, 12)) == ALICE  # higher layer not started yet
    assert on_call(sched, utc(2026, 1, 10, 12)) == DAVE


def test_empty_high_priority_layer_falls_through() -> None:
    sched = schedule(layer((ALICE,), priority=1), layer((), priority=9))
    assert on_call(sched, utc(2026, 1, 6)) == ALICE


def test_schedule_with_no_layers_has_nobody_on_call() -> None:
    assert on_call(schedule(), utc(2026, 1, 6)) is None


# --- render_shifts ---------------------------------------------------------------------------


def test_render_shifts_splits_at_handoffs() -> None:
    shifts = render_shifts(schedule(layer()), utc(2026, 1, 5, 9), utc(2026, 1, 8, 9))
    assert [(s.user_id, s.start, s.end) for s in shifts] == [
        (ALICE, utc(2026, 1, 5, 9), utc(2026, 1, 6, 9)),
        (BOB, utc(2026, 1, 6, 9), utc(2026, 1, 7, 9)),
        (CAROL, utc(2026, 1, 7, 9), utc(2026, 1, 8, 9)),
    ]


def test_render_shifts_merges_equal_neighbours() -> None:
    # A one-person daily rotation has a "handoff" every day, but it's one continuous shift.
    shifts = render_shifts(schedule(layer((ALICE,))), utc(2026, 1, 5, 9), utc(2026, 1, 9, 9))
    assert shifts == [Shift(ALICE, utc(2026, 1, 5, 9), utc(2026, 1, 9, 9), "Primary")]


def test_render_shifts_cuts_around_overrides() -> None:
    sched = schedule(
        layer(),
        overrides=(
            OverrideSpec(user_id=DAVE, start=utc(2026, 1, 5, 12), end=utc(2026, 1, 5, 14), seq=1),
        ),
    )
    shifts = render_shifts(sched, utc(2026, 1, 5, 9), utc(2026, 1, 6, 9))
    assert [(s.user_id, s.start.hour, s.end.hour, s.source) for s in shifts] == [
        (ALICE, 9, 12, "Primary"),
        (DAVE, 12, 14, "override"),
        (ALICE, 14, 9, "Primary"),
    ]


def test_render_shifts_leaves_gaps_where_nobody_is_on_call() -> None:
    shifts = render_shifts(schedule(layer((ALICE,))), utc(2026, 1, 5), utc(2026, 1, 5, 12))
    assert shifts == [Shift(ALICE, utc(2026, 1, 5, 9), utc(2026, 1, 5, 12), "Primary")]


def test_render_shifts_follows_local_handoffs_across_dst() -> None:
    ny = layer((ALICE, BOB), start=utc(2026, 3, 6, 14), tz="America/New_York")
    shifts = render_shifts(schedule(ny), utc(2026, 3, 7, 14), utc(2026, 3, 9, 13))
    assert [(s.user_id, s.start, s.end) for s in shifts] == [
        (BOB, utc(2026, 3, 7, 14), utc(2026, 3, 8, 13)),  # 23-hour shift on DST day
        (ALICE, utc(2026, 3, 8, 13), utc(2026, 3, 9, 13)),
    ]


def test_render_shifts_handles_a_handoff_inside_the_dst_gap() -> None:
    # 02:30 does not exist on 2026-03-08 in New York; the handoff happens at 03:00 EDT
    # (07:00 UTC), the first instant whose local time is at or after 02:30.
    ny = layer(
        (ALICE, BOB), start=utc(2026, 3, 6, 7, 30), handoff=time(2, 30), tz="America/New_York"
    )
    shifts = render_shifts(schedule(ny), utc(2026, 3, 7, 12), utc(2026, 3, 8, 12))
    assert [(s.user_id, s.start, s.end) for s in shifts] == [
        (BOB, utc(2026, 3, 7, 12), utc(2026, 3, 8, 7)),
        (ALICE, utc(2026, 3, 8, 7), utc(2026, 3, 8, 12)),
    ]
    assert layer_user_at(ny, utc(2026, 3, 8, 6, 59)) == BOB
    assert layer_user_at(ny, utc(2026, 3, 8, 7)) == ALICE


def test_render_shifts_for_a_custom_rotation() -> None:
    lay = layer((ALICE, BOB), rotation=Rotation.CUSTOM, turn_length=timedelta(hours=12))
    shifts = render_shifts(schedule(lay), utc(2026, 1, 5, 15), utc(2026, 1, 6, 15))
    assert [(s.user_id, s.start, s.end) for s in shifts] == [
        (ALICE, utc(2026, 1, 5, 15), utc(2026, 1, 5, 21)),
        (BOB, utc(2026, 1, 5, 21), utc(2026, 1, 6, 9)),
        (ALICE, utc(2026, 1, 6, 9), utc(2026, 1, 6, 15)),
    ]


def test_render_shifts_of_an_empty_window_is_empty() -> None:
    assert render_shifts(schedule(layer()), utc(2026, 1, 6), utc(2026, 1, 6)) == []
