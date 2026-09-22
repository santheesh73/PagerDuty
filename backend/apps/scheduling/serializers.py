import zoneinfo

from rest_framework import serializers

from apps.scheduling.models import Schedule, ScheduleRotation
from apps.users.models import Team, TeamMembership, User
from apps.users.serializers import TeamSummarySerializer, UserSummarySerializer


class ScheduleSummarySerializer(serializers.ModelSerializer):
    """Compact representation of a Schedule for nested relationships."""

    class Meta:
        model = Schedule
        fields = ["id", "name", "slug", "timezone", "is_primary", "is_active"]


class ScheduleSerializer(serializers.ModelSerializer):
    """Full operational Schedule representation."""

    team = TeamSummarySerializer(read_only=True)
    team_id = serializers.PrimaryKeyRelatedField(
        queryset=Team.objects.all(),
        source="team",
        write_only=True,
    )

    def to_internal_value(self, data):
        if hasattr(data, "copy"):
            data = data.copy()
        elif isinstance(data, dict):
            data = dict(data)
        if isinstance(data, dict) and "team" in data and "team_id" not in data and not isinstance(data["team"], dict):
            data["team_id"] = data["team"]
        return super().to_internal_value(data)

    class Meta:
        model = Schedule
        fields = [
            "id",
            "name",
            "slug",
            "team",
            "team_id",
            "timezone",
            "is_primary",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise serializers.ValidationError("Schedule name cannot be empty or whitespace.")
        return trimmed

    def validate_slug(self, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise serializers.ValidationError("Schedule slug cannot be empty or whitespace.")
        return trimmed

    def validate_timezone(self, value: str) -> str:
        trimmed = value.strip()
        if trimmed not in zoneinfo.available_timezones():
            raise serializers.ValidationError(f"Invalid timezone '{trimmed}'.")
        return trimmed

    def validate(self, attrs: dict) -> dict:
        team = attrs.get("team") or (self.instance.team if self.instance else None)
        is_active = attrs.get("is_active", self.instance.is_active if self.instance else True)
        is_primary = attrs.get("is_primary", self.instance.is_primary if self.instance else False)

        if is_active and team and not team.is_active:
            raise serializers.ValidationError(
                {"team_id": "Cannot create or activate a schedule for an inactive team."}
            )

        # Primary schedule uniqueness validation
        if is_active and is_primary and team:
            conflict_qs = Schedule.objects.filter(
                team=team,
                is_primary=True,
                is_active=True,
            )
            if self.instance:
                conflict_qs = conflict_qs.exclude(pk=self.instance.pk)
            if conflict_qs.exists():
                raise serializers.ValidationError(
                    {"is_primary": f"An active primary schedule already exists for team '{team.name}'."}
                )

        return attrs


class ScheduleRotationSerializer(serializers.ModelSerializer):
    """Concrete on-call shift rotation representation."""

    schedule = ScheduleSummarySerializer(read_only=True)
    schedule_id = serializers.PrimaryKeyRelatedField(
        queryset=Schedule.objects.all(),
        source="schedule",
        write_only=True,
    )
    user = UserSummarySerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source="user",
        write_only=True,
    )

    def to_internal_value(self, data):
        if hasattr(data, "copy"):
            data = data.copy()
        elif isinstance(data, dict):
            data = dict(data)
        if isinstance(data, dict):
            if "schedule" in data and "schedule_id" not in data and not isinstance(data["schedule"], dict):
                data["schedule_id"] = data["schedule"]
            if "user" in data and "user_id" not in data and not isinstance(data["user"], dict):
                data["user_id"] = data["user"]
        return super().to_internal_value(data)

    class Meta:
        model = ScheduleRotation
        fields = [
            "id",
            "schedule",
            "schedule_id",
            "user",
            "user_id",
            "start_time",
            "end_time",
            "is_override",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs: dict) -> dict:
        from django.utils import timezone

        schedule = attrs.get("schedule") or (self.instance.schedule if self.instance else None)
        user = attrs.get("user") or (self.instance.user if self.instance else None)
        start_time = attrs.get("start_time") or (self.instance.start_time if self.instance else None)
        end_time = attrs.get("end_time") or (self.instance.end_time if self.instance else None)
        is_override = attrs.get("is_override", self.instance.is_override if self.instance else False)

        if start_time and timezone.is_naive(start_time):
            raise serializers.ValidationError({"start_time": "Rotation start_time must be timezone-aware."})
        if end_time and timezone.is_naive(end_time):
            raise serializers.ValidationError({"end_time": "Rotation end_time must be timezone-aware."})

        if start_time and end_time:
            if end_time <= start_time:
                raise serializers.ValidationError({"end_time": "Rotation end_time must be strictly after start_time."})

        if schedule and user:
            if not user.is_active:
                raise serializers.ValidationError({"user_id": f"User '{user.username}' is inactive."})

            is_active_member = TeamMembership.objects.filter(
                team=schedule.team,
                user=user,
                is_active=True,
            ).exists()
            if not is_active_member:
                raise serializers.ValidationError({
                    "user_id": f"User '{user.username}' is not an active member of team '{schedule.team.name}'."
                })

            if start_time and end_time:
                overlap_qs = ScheduleRotation.objects.filter(
                    schedule=schedule,
                    is_override=is_override,
                    start_time__lt=end_time,
                    end_time__gt=start_time,
                )
                if self.instance:
                    overlap_qs = overlap_qs.exclude(pk=self.instance.pk)

                if overlap_qs.exists():
                    rotation_type = "Override" if is_override else "Base"
                    raise serializers.ValidationError(
                        f"{rotation_type} rotation overlaps with an existing {rotation_type.lower()} rotation on this schedule."
                    )

        return attrs
