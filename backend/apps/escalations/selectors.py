from datetime import datetime
from typing import Any

from django.db.models import Prefetch, QuerySet

from apps.accounts.models import User
from apps.schedules.models import Schedule
from apps.schedules.selectors import on_call_user_ids

from .models import EscalationPolicy, EscalationRule, EscalationTarget


def policies_with_rules() -> QuerySet[EscalationPolicy]:
    return EscalationPolicy.objects.prefetch_related(
        Prefetch(
            "rules",
            queryset=EscalationRule.objects.order_by("level").prefetch_related(
                Prefetch(
                    "targets",
                    queryset=EscalationTarget.objects.select_related(
                        "target_user", "target_schedule"
                    ).order_by("position"),
                )
            ),
        ),
        "services",
    )


def oncall_overview(policies: QuerySet[EscalationPolicy], at: datetime) -> list[dict[str, Any]]:
    """For each policy and level: who would be paged if it fired at `at`."""
    policies = policies_with_rules().filter(pk__in=policies.values("pk")).select_related("team")
    schedule_ids = {
        t.target_schedule_id
        for p in policies
        for r in p.rules.all()
        for t in r.targets.all()
        if t.target_schedule_id
    }
    on_call = on_call_user_ids(schedule_ids, at)
    users = User.objects.in_bulk([u for u in on_call.values() if u])
    schedules = Schedule.objects.in_bulk(schedule_ids)

    overview = []
    for policy in policies:
        levels = []
        for rule in policy.rules.all():
            entries: list[dict[str, Any]] = []
            for target in rule.targets.all():
                if target.target_user_id:
                    entries.append({"user": target.target_user, "schedule": None})
                else:
                    sid = target.target_schedule_id
                    uid = on_call.get(sid) if sid else None
                    entries.append(
                        {
                            "user": users.get(uid) if uid else None,
                            "schedule": schedules.get(sid) if sid else None,
                        }
                    )
            levels.append(
                {"level": rule.level, "delay_minutes": rule.delay_minutes, "oncall": entries}
            )
        overview.append({"policy": policy, "levels": levels})
    return overview
