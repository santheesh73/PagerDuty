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


def test_seed_demo_is_idempotent_and_resettable() -> None:
    from io import StringIO

    from django.core.management import call_command

    from apps.accounts.models import Team, User
    from apps.incidents.models import Incident

    call_command("seed_demo", stdout=StringIO())
    first = Incident.objects.count()
    out = StringIO()
    call_command("seed_demo", stdout=out)
    assert "already present" in out.getvalue()
    assert Incident.objects.count() == first

    call_command("seed_demo", "--reset", stdout=StringIO())
    assert Team.objects.count() == 3
    assert User.objects.filter(email="responder@demo.local").exists()
    assert Incident.objects.exclude(status="resolved").count() == 4

    key_out = StringIO()
    call_command("routing_key", "checkout-api", stdout=key_out)
    assert len(key_out.getvalue().strip()) == 64
