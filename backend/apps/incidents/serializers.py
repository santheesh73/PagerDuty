from rest_framework import serializers

from apps.services.serializers import ServiceSummarySerializer
from apps.users.serializers import UserSummarySerializer

from .models import Incident, IncidentEvent


class IncidentEventSerializer(serializers.ModelSerializer):
    """Immutable event log record for incident timeline inspection."""

    incident_id = serializers.IntegerField(source="incident.id", read_only=True)
    actor = UserSummarySerializer(read_only=True)

    class Meta:
        model = IncidentEvent
        fields = [
            "id",
            "incident_id",
            "event_type",
            "actor",
            "metadata",
            "created_at",
        ]
        read_only_fields = fields


class IncidentSummarySerializer(serializers.ModelSerializer):
    """Compact incident representation for references and foreign relations."""

    class Meta:
        model = Incident
        fields = [
            "id",
            "title",
            "severity",
            "status",
            "triggered_at",
        ]
        read_only_fields = fields


class IncidentSerializer(serializers.ModelSerializer):
    """Detailed operational incident representation."""

    service = ServiceSummarySerializer(read_only=True)
    assigned_user = UserSummarySerializer(read_only=True)
    alert_count = serializers.IntegerField(read_only=True, default=0)
    current_escalation_level = serializers.IntegerField(
        source="current_escalation_level.order", read_only=True, allow_null=True
    )

    class Meta:
        model = Incident
        fields = [
            "id",
            "title",
            "service",
            "severity",
            "status",
            "assigned_user",
            "current_escalation_level",
            "fingerprint",
            "triggered_at",
            "acknowledged_at",
            "resolved_at",
            "alert_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
