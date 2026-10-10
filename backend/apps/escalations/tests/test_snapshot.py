import pytest

from apps.escalations.snapshot import build_snapshot, next_step
from tests.factories import ServiceFactory

SNAP = {"v": 1, "num_loops": 1, "rules": [{"level": 0}, {"level": 1}]}


@pytest.mark.parametrize(
    ("level", "loop", "expected"),
    [(0, 0, (1, 0)), (1, 0, (0, 1)), (0, 1, (1, 1)), (1, 1, None)],
)
def test_next_step_walks_levels_then_loops(
    level: int, loop: int, expected: tuple[int, int] | None
) -> None:
    assert next_step(SNAP, level, loop) == expected


def test_next_step_on_an_empty_policy_is_exhausted() -> None:
    assert next_step({"rules": [], "num_loops": 3}, 0, 0) is None


@pytest.mark.django_db
def test_snapshot_captures_structure_and_target_identities() -> None:
    policy = ServiceFactory().escalation_policy
    snap = build_snapshot(policy)

    assert snap["v"] == 1
    assert snap["policy_id"] == policy.pk
    assert [r["level"] for r in snap["rules"]] == [0, 1]
    assert [r["delay_minutes"] for r in snap["rules"]] == [5, 10]
    assert snap["rules"][0]["targets"][0]["type"] == "schedule"
    assert snap["rules"][1]["targets"][0]["type"] == "user"


def test_snapshot_of_no_policy_is_empty() -> None:
    assert build_snapshot(None)["rules"] == []


@pytest.mark.django_db
def test_simulate_escalation_command_walks_two_levels_and_rolls_back() -> None:
    from io import StringIO

    from django.core.management import call_command

    from apps.incidents.models import Incident

    out = StringIO()
    call_command("simulate_escalation", stdout=out)
    assert "level 3  assignee=Cleo" in out.getvalue()
    assert Incident.objects.count() == 0
