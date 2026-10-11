import os
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from hypothesis import HealthCheck, settings
from rest_framework.test import APIClient

from apps.accounts.models import Membership, User
from apps.alerting.actions import Event, IngestResult, ingest
from apps.catalog.models import Service
from apps.escalations.models import EscalationTarget
from apps.incidents.models import Incident
from apps.schedules.models import LayerMember
from tests.factories import ServiceFactory

# Hypothesis: CI is derandomized (a fixed seed derived from each test) so a property can
# never pass on one run and fail on the next; local runs explore new examples every time.
settings.register_profile(
    "ci",
    derandomize=True,
    deadline=None,
    print_blob=True,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.register_profile("dev", deadline=None, suppress_health_check=[HealthCheck.too_slow])
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))

# A Wednesday. The default factory schedule rotates daily at 09:00 UTC from Monday Jan 5,
# so at T0 the first of its two responders is on call.
T0 = datetime(2026, 1, 7, 12, 0, tzinfo=UTC)


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def service(db: None) -> Service:
    """L0 → on-call schedule (5 min), L1 → team admin (10 min), no loops."""
    return ServiceFactory()


class Paging:
    """Named handles on the people in `service`'s default policy."""

    def __init__(self, service: Service) -> None:
        rules = list(service.escalation_policy.rules.order_by("level"))
        l0 = EscalationTarget.objects.get(rule=rules[0])
        self.schedule = l0.target_schedule
        members = LayerMember.objects.filter(layer__schedule=self.schedule).order_by("position")
        self.on_call, self.off_call = (m.user for m in members)  # at T0
        self.admin = EscalationTarget.objects.get(rule=rules[1]).target_user
        self.responder = self.on_call
        self.viewer = Membership.objects.create(
            team=service.team,
            role=Membership.Role.VIEWER,
            user=User.objects.create_user("viewer@example.test", "pw", name="Viewer"),
        ).user


@pytest.fixture
def people(service: Service) -> Paging:
    return Paging(service)


TriggerFn = Callable[..., IngestResult]


@pytest.fixture
def trigger(db: None) -> TriggerFn:
    def _trigger(
        service: Service,
        dedup_key: str | None = "disk-full",
        *,
        severity: str = "critical",
        summary: str = "Disk 95% full on db-1",
        now: datetime = T0,
        action: str = "trigger",
    ) -> IngestResult:
        return ingest(
            service,
            Event(
                action=action,
                dedup_key=dedup_key,
                summary=summary,
                severity=severity,
                source="pytest",
            ),
            now=now,
        )

    return _trigger


@pytest.fixture
def open_incident(service: Service, trigger: TriggerFn) -> Incident:
    result = trigger(service)
    return Incident.objects.get(pk=result.incident_id)
