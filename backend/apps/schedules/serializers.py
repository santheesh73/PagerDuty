from datetime import datetime, timedelta
from typing import Any

from django.db import transaction
from rest_framework import serializers

from apps.accounts.models import Membership, Team
from apps.accounts.serializers import UserSummarySerializer
from apps.core import limits
from apps.core.scoping import ScopedPrimaryKeyRelatedField

from .models import (
    LAYER_START_MAX,
    LAYER_START_MIN,
    LayerMember,
    Rotation,
    Schedule,
    ScheduleLayer,
    ScheduleOverride,
)


class LayerSerializer(serializers.ModelSerializer):
    """A rotation layer. `members` is the rotation order as user ids."""

    members = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=True)
    member_details = UserSummarySerializer(many=True, read_only=True)
    turn_length_hours = serializers.IntegerField(
        min_value=1,
        max_value=24 * 28,
        required=False,
        allow_null=True,
        help_text="Custom rotations only: hours per turn.",
    )

    class Meta:
        model = ScheduleLayer
        fields = [
            "id",
            "name",
            "priority",
            "rotation_type",
            "turn_count",
            "turn_length_hours",
            "start",
            "handoff_time",
            "members",
            "member_details",
        ]
        read_only_fields = ["id", "priority", "member_details"]

    def to_representation(self, instance: ScheduleLayer) -> dict[str, Any]:
        members = [m.user for m in instance.members.all()]
        return {
            "id": instance.pk,
            "name": instance.name,
            "priority": instance.priority,
            "rotation_type": instance.rotation_type,
            "turn_count": instance.turn_count,
            "turn_length_hours": (
                int(instance.turn_length.total_seconds() // 3600) if instance.turn_length else None
            ),
            "start": serializers.DateTimeField().to_representation(instance.start),
            "handoff_time": instance.handoff_time.strftime("%H:%M:%S"),
            "members": [u.pk for u in members],
            "member_details": UserSummarySerializer(members, many=True).data,
        }

    def validate_start(self, value: datetime) -> datetime:
        if not LAYER_START_MIN <= value < LAYER_START_MAX:
            raise serializers.ValidationError(
                f"Start must be between {LAYER_START_MIN:%Y-%m-%d} and {LAYER_START_MAX:%Y-%m-%d}."
            )
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        limits.enforce("members_per_layer", len(attrs.get("members", [])))
        if attrs["rotation_type"] == Rotation.CUSTOM and not attrs.get("turn_length_hours"):
            raise serializers.ValidationError(
                {"turn_length_hours": "Custom rotations need a turn length."}
            )
        return attrs


class ScheduleSerializer(serializers.ModelSerializer):
    """Writes replace `layers` wholesale. Layer order is priority: the first layer wins."""

    team = ScopedPrimaryKeyRelatedField(queryset=Team.objects.all(), team_lookup="id")
    layers = LayerSerializer(many=True)

    class Meta:
        model = Schedule
        fields = ["id", "team", "name", "timezone", "layers", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_layers(self, layers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        limits.enforce("layers_per_schedule", len(layers))
        return layers

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        team = attrs.get("team") or getattr(self.instance, "team", None)
        if self.instance is not None and "team" in attrs and attrs["team"] != self.instance.team:
            raise serializers.ValidationError({"team": "A schedule cannot move between teams."})
        member_ids = {uid for layer in attrs.get("layers", []) for uid in layer["members"]}
        known = set(
            Membership.objects.filter(team=team, user_id__in=member_ids).values_list(
                "user_id", flat=True
            )
        )
        if missing := member_ids - known:
            raise serializers.ValidationError(
                {"layers": f"Users {sorted(missing)} are not members of this team."}
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data: dict[str, Any]) -> Schedule:
        layers = validated_data.pop("layers")
        schedule = Schedule.objects.create(**validated_data)
        self._replace_layers(schedule, layers)
        return schedule

    @transaction.atomic
    def update(self, instance: Schedule, validated_data: dict[str, Any]) -> Schedule:
        layers = validated_data.pop("layers", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if layers is not None:
            self._replace_layers(instance, layers)
        return instance

    @staticmethod
    def _replace_layers(schedule: Schedule, layers: list[dict[str, Any]]) -> None:
        schedule.layers.all().delete()
        for index, data in enumerate(layers):
            hours = data.get("turn_length_hours")
            layer = ScheduleLayer.objects.create(
                schedule=schedule,
                name=data["name"],
                priority=len(layers) - index,
                rotation_type=data["rotation_type"],
                turn_count=data.get("turn_count", 1),
                turn_length=(
                    timedelta(hours=hours)
                    if data["rotation_type"] == Rotation.CUSTOM and hours
                    else None
                ),
                start=data["start"],
                handoff_time=data["handoff_time"],
            )
            LayerMember.objects.bulk_create(
                LayerMember(layer=layer, user_id=uid, position=pos)
                for pos, uid in enumerate(data["members"])
            )


class OverrideSerializer(serializers.ModelSerializer):
    user_detail = UserSummarySerializer(source="user", read_only=True)

    class Meta:
        model = ScheduleOverride
        fields = ["id", "user", "user_detail", "start", "end", "created_at"]
        read_only_fields = ["id", "user_detail", "created_at"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        start = attrs.get("start", getattr(self.instance, "start", None))
        end = attrs.get("end", getattr(self.instance, "end", None))
        if start and end and end <= start:
            raise serializers.ValidationError({"end": "End must be after start."})
        schedule: Schedule = self.context["schedule"]
        user = attrs.get("user")
        if user and not Membership.objects.filter(team=schedule.team, user=user).exists():
            raise serializers.ValidationError({"user": "Not a member of this schedule's team."})
        return attrs


class ShiftSerializer(serializers.Serializer):
    user = UserSummarySerializer()
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    source = serializers.CharField()  # type: ignore[assignment]  # field named like Field.source


class OnCallNowSerializer(serializers.Serializer):
    at = serializers.DateTimeField()
    user = UserSummarySerializer(allow_null=True)
    source = serializers.CharField(allow_null=True)  # type: ignore[assignment]
