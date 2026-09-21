from rest_framework import serializers

from apps.users.models import TeamMembership

from .models import EscalationLevel, EscalationPolicy


class EscalationLevelSerializer(serializers.ModelSerializer):
    target_username = serializers.CharField(source="target_user.username", read_only=True)

    class Meta:
        model = EscalationLevel
        fields = [
            "id",
            "policy",
            "order",
            "target_type",
            "target_user",
            "target_username",
            "wait_minutes",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        policy = attrs.get("policy") or (instance.policy if instance else None)
        order = attrs.get("order", instance.order if instance else None)
        wait_minutes = attrs.get("wait_minutes", instance.wait_minutes if instance else None)
        target_type = attrs.get("target_type", instance.target_type if instance else EscalationLevel.TargetType.CURRENT_ON_CALL)
        target_user = attrs.get("target_user", instance.target_user if instance else None)

        if order is not None and order < 1:
            raise serializers.ValidationError({"order": "Order must be a positive integer starting at 1."})

        if wait_minutes is not None and wait_minutes < 0:
            raise serializers.ValidationError({"wait_minutes": "Wait minutes must be non-negative."})

        if target_type == EscalationLevel.TargetType.USER:
            if not target_user:
                raise serializers.ValidationError({"target_user": "Target user is required when target_type is USER."})
            if not target_user.is_active:
                raise serializers.ValidationError({"target_user": "Target user must be active."})
            if policy and policy.team_id:
                is_member = TeamMembership.objects.filter(
                    team=policy.team,
                    user=target_user,
                    is_active=True,
                ).exists()
                if not is_member:
                    raise serializers.ValidationError(
                        {"target_user": f"User {target_user.username} is not an active member of team {policy.team.name}."}
                    )
        elif target_type == EscalationLevel.TargetType.CURRENT_ON_CALL:
            if target_user is not None:
                raise serializers.ValidationError({"target_user": "Target user must be null when target_type is CURRENT_ON_CALL."})

        return attrs


class EscalationPolicySerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source="team.name", read_only=True)
    levels = EscalationLevelSerializer(many=True, read_only=True)

    class Meta:
        model = EscalationPolicy
        fields = [
            "id",
            "name",
            "slug",
            "team",
            "team_name",
            "is_active",
            "levels",
            "created_at",
            "updated_at",
        ]
