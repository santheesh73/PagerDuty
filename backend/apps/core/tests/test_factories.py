import pytest

from apps.accounts.models import Membership
from apps.escalations.models import EscalationTarget
from apps.schedules.models import LayerMember
from tests.factories import (
    AlertFactory,
    IncidentEventFactory,
    NotificationFactory,
    ScheduleOverrideFactory,
    ServiceFactory,
)

pytestmark = pytest.mark.django_db


def test_service_factory_builds_a_complete_pageable_graph() -> None:
    service = ServiceFactory()

    policy = service.escalation_policy
    assert policy.team == service.team
    rules = list(policy.rules.order_by("level"))
    assert [r.level for r in rules] == [0, 1]

    l0_target = EscalationTarget.objects.get(rule=rules[0])
    assert l0_target.target_schedule is not None
    members = LayerMember.objects.filter(layer__schedule=l0_target.target_schedule)
    assert members.count() == 2
    assert Membership.objects.filter(team=service.team).count() == 3
    assert len(service.integration_key) == 64


def test_every_remaining_factory_builds() -> None:
    assert AlertFactory().pk
    assert IncidentEventFactory().incident.number >= 1
    assert NotificationFactory().pk
    assert ScheduleOverrideFactory().end > ScheduleOverrideFactory().start
