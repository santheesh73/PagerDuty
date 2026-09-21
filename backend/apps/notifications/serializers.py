from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for auditing and inspecting dispatched notifications.
    """

    incident_title = serializers.CharField(source="incident.title", read_only=True)
    recipient_username = serializers.CharField(source="recipient.username", read_only=True)
    recipient_email = serializers.CharField(source="recipient.email", read_only=True)
    escalation_level_order = serializers.IntegerField(
        source="escalation_level.order", read_only=True, allow_null=True
    )

    class Meta:
        model = Notification
        fields = [
            "id",
            "incident",
            "incident_title",
            "recipient",
            "recipient_username",
            "recipient_email",
            "channel",
            "status",
            "escalation_level",
            "escalation_level_order",
            "dedupe_key",
            "attempt_count",
            "sent_at",
            "failed_at",
            "last_error",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
