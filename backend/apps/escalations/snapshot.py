"""Freeze a policy's *structure* when an incident opens.

The snapshot pins levels, delays, loop count and target identities. It deliberately does
not pin people: a schedule target still resolves to whoever is on call at the moment each
level fires. So editing the live policy never rewires an incident already in flight, but a
shift handoff during the incident still routes to the new on-call.

Format v1:
    {"v": 1, "policy_id": 4, "policy_name": "Payments primary", "num_loops": 1,
     "rules": [{"level": 0, "delay_minutes": 5, "targets": [{"type": "schedule", "id": 3}]}]}
"""

from typing import Any, TypedDict

from .models import EscalationPolicy

SNAPSHOT_VERSION = 1


class TargetRef(TypedDict):
    type: str  # "user" | "schedule"
    id: int


class RuleSnapshot(TypedDict):
    level: int
    delay_minutes: int
    targets: list[TargetRef]


def build_snapshot(policy: EscalationPolicy | None) -> dict[str, Any]:
    if policy is None:
        return {
            "v": SNAPSHOT_VERSION,
            "policy_id": None,
            "policy_name": "",
            "num_loops": 0,
            "rules": [],
        }
    rules: list[RuleSnapshot] = []
    for rule in policy.rules.order_by("level").prefetch_related("targets"):
        targets = [
            TargetRef(type=t.kind, id=t.target_id)
            for t in sorted(rule.targets.all(), key=lambda t: t.position)
        ]
        rules.append(
            RuleSnapshot(level=rule.level, delay_minutes=rule.delay_minutes, targets=targets)
        )
    return {
        "v": SNAPSHOT_VERSION,
        "policy_id": policy.pk,
        "policy_name": policy.name,
        "num_loops": policy.num_loops,
        "rules": rules,
    }


def next_step(snapshot: dict[str, Any], level: int, loop: int) -> tuple[int, int] | None:
    """Where escalation goes after (level, loop), or None when the policy is exhausted."""
    rules = snapshot.get("rules") or []
    if level + 1 < len(rules):
        return level + 1, loop
    if rules and loop < snapshot.get("num_loops", 0):
        return 0, loop + 1
    return None
