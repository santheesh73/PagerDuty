from typing import Any

from django.db import transaction
from rest_framework import serializers

from apps.accounts.models import Membership, Team, User
from apps.core import limits
from apps.core.scoping import ScopedPrimaryKeyRelatedField
from apps.schedules.models import Schedule

from .models import EscalationPolicy, EscalationRule, EscalationTarget


class TargetSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=EscalationTarget.Kind.choices)
    id = serializers.IntegerField(min_value=1)
    name = serializers.CharField(read_only=True)

    def to_representation(self, instance: EscalationTarget) -> dict[str, Any]:
        named = instance.target_user or instance.target_schedule
        return {"type": instance.kind, "id": instance.target_id, "name": str(named or "")}


class RuleSerializer(serializers.Serializer):
    level = serializers.IntegerField(read_only=True)
    delay_minutes = serializers.IntegerField(min_value=1, max_value=24 * 60)
    targets = TargetSerializer(many=True)


class PolicyServiceSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)


class EscalationPolicySerializer(serializers.ModelSerializer):
    """A policy and its ordered levels. Writes replace `rules` wholesale, atomically."""

    team = ScopedPrimaryKeyRelatedField(queryset=Team.objects.all(), team_lookup="id")
    rules = RuleSerializer(many=True)
    services = PolicyServiceSerializer(many=True, read_only=True)

    class Meta:
        model = EscalationPolicy
        fields = [
            "id",
            "team",
            "name",
            "num_loops",
            "rules",
            "services",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "services", "created_at", "updated_at"]

    def validate_rules(self, rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
        limits.enforce("levels_per_policy", len(rules))
        for index, rule in enumerate(rules):
            if not rule["targets"]:
                raise serializers.ValidationError(f"Level {index + 1} needs at least one target.")
            limits.enforce("targets_per_level", len(rule["targets"]))
        return rules

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        team = attrs.get("team") or getattr(self.instance, "team", None)
        if self.instance is not None and "team" in attrs and attrs["team"] != self.instance.team:
            raise serializers.ValidationError({"team": "A policy cannot move between teams."})
        for rule in attrs.get("rules", []):
            for target in rule["targets"]:
                self._check_target_in_team(target, team)
        return attrs

    @staticmethod
    def _check_target_in_team(target: dict[str, Any], team: Team | None) -> None:
        if target["type"] == EscalationTarget.Kind.USER:
            ok = Membership.objects.filter(team=team, user_id=target["id"]).exists()
        else:
            ok = Schedule.objects.filter(team=team, pk=target["id"]).exists()
        if not ok:
            raise serializers.ValidationError(
                {"rules": f"{target['type']} {target['id']} is not part of this team."}
            )

    @transaction.atomic
    def create(self, validated_data: dict[str, Any]) -> EscalationPolicy:
        rules = validated_data.pop("rules")
        policy = EscalationPolicy.objects.create(**validated_data)
        self._replace_rules(policy, rules)
        return policy

    @transaction.atomic
    def update(
        self, instance: EscalationPolicy, validated_data: dict[str, Any]
    ) -> EscalationPolicy:
        rules = validated_data.pop("rules", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if rules is not None:
            self._replace_rules(instance, rules)
        return instance

    @staticmethod
    def _replace_rules(policy: EscalationPolicy, rules: list[dict[str, Any]]) -> None:
        # Open incidents carry their own snapshot, so replacing rules can't affect them.
        policy.rules.all().delete()
        users = User.objects.in_bulk(
            [t["id"] for r in rules for t in r["targets"] if t["type"] == "user"]
        )
        schedules = Schedule.objects.in_bulk(
            [t["id"] for r in rules for t in r["targets"] if t["type"] == "schedule"]
        )
        for level, rule in enumerate(rules):
            row = EscalationRule.objects.create(
                policy=policy, level=level, delay_minutes=rule["delay_minutes"]
            )
            EscalationTarget.objects.bulk_create(
                EscalationTarget(
                    rule=row,
                    position=position,
                    target_user=users.get(t["id"]) if t["type"] == "user" else None,
                    target_schedule=schedules.get(t["id"]) if t["type"] == "schedule" else None,
                )
                for position, t in enumerate(rule["targets"])
            )
