from rest_framework import serializers

from .models import Team, TeamMembership, User


class UserSummarySerializer(serializers.ModelSerializer):
    """Compact user representation for nested relationships."""

    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "name", "email"]

    def get_name(self, obj: User) -> str:
        return obj.get_full_name().strip() or obj.username


class UserSerializer(serializers.ModelSerializer):
    """Full user representation."""

    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "name",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "date_joined",
        ]
        read_only_fields = ["id", "date_joined"]

    def get_name(self, obj: User) -> str:
        return obj.get_full_name().strip() or obj.username


class TeamSummarySerializer(serializers.ModelSerializer):
    """Compact team representation for nested relationships."""

    class Meta:
        model = Team
        fields = ["id", "name", "slug", "is_active"]


class TeamSerializer(serializers.ModelSerializer):
    """Team representation including operational metadata and member count."""

    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "is_active",
            "member_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_member_count(self, obj: Team) -> int:
        if hasattr(obj, "active_member_count"):
            return obj.active_member_count
        return obj.memberships.filter(is_active=True).count()

    def validate_name(self, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise serializers.ValidationError("Team name cannot be empty or whitespace.")
        return trimmed

    def validate_slug(self, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise serializers.ValidationError("Team slug cannot be empty or whitespace.")
        return trimmed


class TeamMembershipSerializer(serializers.ModelSerializer):
    """
    Explicit team membership serializer.
    Handles read representation with nested entities and write inputs via primary keys.
    """

    user = UserSummarySerializer(read_only=True)
    team = TeamSummarySerializer(read_only=True)

    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source="user",
        write_only=True,
    )
    team_id = serializers.PrimaryKeyRelatedField(
        queryset=Team.objects.all(),
        source="team",
        write_only=True,
    )

    class Meta:
        model = TeamMembership
        fields = [
            "id",
            "user",
            "team",
            "user_id",
            "team_id",
            "role",
            "is_active",
            "joined_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "joined_at", "created_at", "updated_at"]

    def validate_role(self, value: str) -> str:
        if value not in TeamMembership.Role.values:
            valid_roles = ", ".join(TeamMembership.Role.values)
            raise serializers.ValidationError(
                f"Invalid role '{value}'. Must be one of: {valid_roles}."
            )
        return value

    def validate(self, attrs: dict) -> dict:
        user = attrs.get("user") or (self.instance.user if self.instance else None)
        team = attrs.get("team") or (self.instance.team if self.instance else None)
        is_active = attrs.get("is_active", self.instance.is_active if self.instance else True)

        # Inactive validation on creation or activation
        if is_active:
            if user and not user.is_active:
                raise serializers.ValidationError(
                    {"user_id": "Cannot assign membership to an inactive user."}
                )
            if team and not team.is_active:
                raise serializers.ValidationError(
                    {"team_id": "Cannot assign membership to an inactive team."}
                )

        # Duplicate check on creation
        if not self.instance:
            if user and team and TeamMembership.objects.filter(user=user, team=team).exists():
                raise serializers.ValidationError(
                    {"non_field_errors": ["User is already a member of this team."]}
                )

        return attrs
