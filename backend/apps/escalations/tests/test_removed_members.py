"""A person removed from a team is not paged by that team's rotations or policies.

Targets are validated as team members when a policy is saved, but nothing re-checked at paging
time: someone removed afterwards kept being woken by the rotation they were still listed in
(found by the final audit)."""

import pytest

from apps.accounts.models import Membership
from apps.notifications.models import Notification
from conftest import Paging, TriggerFn

pytestmark = pytest.mark.django_db


def test_a_removed_team_member_is_not_paged(service, trigger: TriggerFn, people: Paging) -> None:
    Membership.objects.filter(user=people.on_call, team=service.team).delete()
    result = trigger(service)
    paged = set(
        Notification.objects.filter(incident_id=result.incident_id).values_list(
            "user_id", flat=True
        )
    )
    assert people.on_call.pk not in paged


def test_a_current_team_member_is_paged(service, trigger: TriggerFn, people: Paging) -> None:
    result = trigger(service)
    paged = set(
        Notification.objects.filter(incident_id=result.incident_id).values_list(
            "user_id", flat=True
        )
    )
    assert people.on_call.pk in paged
