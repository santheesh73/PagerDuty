from rest_framework import serializers

from apps.users.models import Team
from apps.users.serializers import TeamSummarySerializer

from .models import Service


class ServiceSummarySerializer(serializers.ModelSerializer):
    """Compact representation of a Service for nested relationships."""

    class Meta:
        model = Service
        fields = ["id", "name", "slug", "status"]


class ServiceSerializer(serializers.ModelSerializer):
    """Full operational Service representation."""

    team = TeamSummarySerializer(read_only=True)
    team_id = serializers.PrimaryKeyRelatedField(
        queryset=Team.objects.all(),
        source="team",
        write_only=True,
    )
    status = serializers.CharField(required=False, default=Service.Status.HEALTHY)

    def to_internal_value(self, data):
        if hasattr(data, "copy"):
            data = data.copy()
        elif isinstance(data, dict):
            data = dict(data)
        if isinstance(data, dict) and "team" in data and "team_id" not in data and not isinstance(data["team"], dict):
            data["team_id"] = data["team"]
        return super().to_internal_value(data)

    class Meta:
        model = Service
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "team",
            "team_id",
            "status",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise serializers.ValidationError("Service name cannot be empty or whitespace.")
        return trimmed

    def validate_slug(self, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise serializers.ValidationError("Service slug cannot be empty or whitespace.")
        return trimmed

    def validate_status(self, value: str) -> str:
        canonical = value.strip().upper()
        if canonical not in Service.Status.values:
            valid_statuses = ", ".join(Service.Status.values)
            raise serializers.ValidationError(
                f"Invalid status '{value}'. Must be one of: {valid_statuses}."
            )
        return canonical

    def validate(self, attrs: dict) -> dict:
        team = attrs.get("team") or (self.instance.team if self.instance else None)
        is_active = attrs.get("is_active", self.instance.is_active if self.instance else True)

        if is_active and team and not team.is_active:
            raise serializers.ValidationError(
                {"team_id": "Cannot assign an active Service to an inactive Team."}
            )

        return attrs
