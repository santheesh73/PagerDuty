"""One definition of "is Pulse actually doing its job?", shared by `manage.py selfcheck`
(cron/CI/ops) and the Beat heartbeat (which only pings the dead-man's switch when it passes).

Liveness probes ask "is the process up"; these ask the questions that matter for an
incident tool: is the escalation timer being honoured, and are pages being delivered?
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import connection
from django.utils import timezone

from apps.core import heartbeat
from apps.incidents.models import Incident, Status
from apps.notifications.models import Notification

SWEEPER_LAG_LIMIT = 120.0  # seconds; the sweeper runs every 30 s
STUCK_AFTER = timedelta(minutes=5)  # pending this long means redelivery is not working


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def sweeper_lag_seconds(now: datetime) -> float:
    """How long the most overdue open escalation has been overdue (0 when none is)."""
    from django.db.models import Min

    oldest = Incident.objects.filter(
        status=Status.TRIGGERED, next_escalation_at__lte=now
    ).aggregate(oldest=Min("next_escalation_at"))["oldest"]
    return max(0.0, (now - oldest).total_seconds()) if oldest else 0.0


def overdue_escalations(now: datetime) -> int:
    return Incident.objects.filter(status=Status.TRIGGERED, next_escalation_at__lte=now).count()


def stuck_notifications(now: datetime) -> int:
    return Notification.objects.filter(
        status=Notification.Status.PENDING, updated_at__lt=now - STUCK_AFTER
    ).count()


def run(*, include_beat: bool = True, now: datetime | None = None) -> list[Check]:
    now = now or timezone.now()
    checks: list[Check] = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks.append(Check("database", True, "reachable"))
    except Exception as exc:
        return [Check("database", False, type(exc).__name__)]

    lag = sweeper_lag_seconds(now)
    checks.append(Check("escalation sweeper", lag <= SWEEPER_LAG_LIMIT, f"max overdue {lag:.0f}s"))
    stuck = stuck_notifications(now)
    checks.append(Check("notification delivery", stuck == 0, f"{stuck} stuck pending"))
    if include_beat:
        last = heartbeat.last_run()
        age = None if last is None else now.timestamp() - last
        checks.append(
            Check(
                "beat heartbeat",
                age is not None and age <= heartbeat.BEAT_STALE_AFTER,
                "never seen" if age is None else f"{age:.0f}s ago",
            )
        )
    return checks
