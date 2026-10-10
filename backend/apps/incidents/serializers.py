from typing import Any

from rest_framework import serializers

from apps.accounts.models import User
from apps.accounts.serializers import UserSummarySerializer
from apps.alerting.models import Alert
from apps.core.limits import MAX_NOTE_LENGTH
from apps.core.permissions import Role, has_role

from .actions import allowed_actions
from .models import Incident, IncidentEvent
from .selectors import snapshot_with_names


class IncidentServiceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    mode = serializers.CharField()
    team = serializers.IntegerField(source="team_id")


class IncidentSerializer(serializers.ModelSerializer):
    service = IncidentServiceSerializer(read_only=True)
    assignee = UserSummarySerializer(read_only=True, allow_null=True)
    allowed_actions = serializers.SerializerMethodField(
        help_text="Actions the requester may take right now, given status and team role."
    )

    class Meta:
        model = Incident
        fields = [
            "id",
            "number",
            "title",
            "status",
            "urgency",
            "service",
            "assignee",
            "dedup_key",
            "is_maintenance",
            "escalation_level",
            "escalation_loop",
            "next_escalation_at",
            "triggered_at",
            "first_response_at",
            "acknowledged_at",
            "resolved_at",
            "alert_count",
            "allowed_actions",
        ]
        read_only_fields = fields

    def get_allowed_actions(self, obj: Incident) -> list[str]:
        request = self.context.get("request")
        if not request or not has_role(request.user, obj.service.team_id, Role.RESPONDER):
            return []
        return allowed_actions(obj.status)


class IncidentDetailSerializer(IncidentSerializer):
    escalation_snapshot = serializers.SerializerMethodField()

    class Meta(IncidentSerializer.Meta):
        fields = [*IncidentSerializer.Meta.fields, "escalation_snapshot"]
        read_only_fields = fields

    def get_escalation_snapshot(self, obj: Incident) -> dict[str, Any]:
        return snapshot_with_names(obj)


class IncidentEventSerializer(serializers.ModelSerializer):
    actor = UserSummarySerializer(read_only=True, allow_null=True)

    class Meta:
        model = IncidentEvent
        fields = ["id", "type", "actor", "message", "data", "created_at"]
        read_only_fields = fields


class AlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = [
            "id",
            "dedup_key",
            "severity",
            "summary",
            "source",
            "payload",
            "status",
            "received_at",
        ]
        read_only_fields = fields


class ReassignSerializer(serializers.Serializer):
    assignee = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(is_active=True))


class NoteSerializer(serializers.Serializer):
    # No max_length here: the limit is enforced by core.limits so it returns limit_exceeded.
    text = serializers.CharField(trim_whitespace=True, help_text=f"≤ {MAX_NOTE_LENGTH} chars")
