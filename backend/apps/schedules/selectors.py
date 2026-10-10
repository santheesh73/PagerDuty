from collections.abc import Iterable
from datetime import datetime

from django.db.models import Prefetch, QuerySet

from .models import LayerMember, Schedule, ScheduleLayer, ScheduleOverride
from .oncall import LayerSpec, OverrideSpec, ScheduleSpec, Shift, on_call, render_shifts


def schedules_with_layers() -> QuerySet[Schedule]:
    return Schedule.objects.prefetch_related(
        Prefetch(
            "layers",
            queryset=ScheduleLayer.objects.prefetch_related(
                Prefetch("members", queryset=LayerMember.objects.order_by("position"))
            ).order_by("-priority"),
        )
    )


def load_schedule_spec(
    schedule: Schedule, *, since: datetime, until: datetime | None = None
) -> ScheduleSpec:
    """Snapshot the rows `oncall.py` needs. Only overrides overlapping [since, until] load."""
    until = until or since
    layers = tuple(
        LayerSpec(
            name=layer.name,
            priority=layer.priority,
            rotation_type=layer.rotation_type,
            turn_count=layer.turn_count,
            turn_length=layer.turn_length,
            start=layer.start,
            handoff_time=layer.handoff_time,
            timezone=schedule.timezone,
            members=tuple(m.user_id for m in layer.members.all()),
        )
        for layer in schedule.layers.all()
    )
    overrides = tuple(
        OverrideSpec(user_id=o.user_id, start=o.start, end=o.end, seq=o.pk)
        for o in ScheduleOverride.objects.filter(
            schedule=schedule, start__lte=until, end__gt=since
        ).only("user_id", "start", "end")
    )
    return ScheduleSpec(layers=layers, overrides=overrides)


def on_call_user_ids(schedule_ids: Iterable[int], at: datetime) -> dict[int, int | None]:
    """{schedule_id: user_id on call at `at`} in a fixed number of queries."""
    schedules = schedules_with_layers().filter(pk__in=list(schedule_ids))
    return {s.pk: on_call(load_schedule_spec(s, since=at), at) for s in schedules}


def shifts_for(schedule: Schedule, since: datetime, until: datetime) -> list[Shift]:
    spec = load_schedule_spec(schedule, since=since, until=until)
    return render_shifts(spec, since, until)
