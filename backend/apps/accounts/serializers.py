from rest_framework import serializers

from .models import Membership, Team, User


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "name", "email", "timezone"]
        read_only_fields = fields


class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ["id", "name", "slug"]
        read_only_fields = fields


class MembershipSerializer(serializers.ModelSerializer):
    team = TeamSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ["team", "role"]
        read_only_fields = fields


class TeamMemberSerializer(serializers.ModelSerializer):
    user = UserSummarySerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ["user", "role"]
        read_only_fields = fields


class MeSerializer(serializers.ModelSerializer):
    memberships = MembershipSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "name", "timezone", "is_staff", "memberships"]
        read_only_fields = ["id", "email", "is_staff", "memberships"]


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, style={"input_type": "password"})
