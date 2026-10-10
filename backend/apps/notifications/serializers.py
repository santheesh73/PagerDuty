from rest_framework import serializers

from .models import Notification


class IncidentRefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    number = serializers.IntegerField()
    title = serializers.CharField()
    status = serializers.CharField()
    urgency = serializers.CharField()


class NotificationSerializer(serializers.ModelSerializer):
    incident = IncidentRefSerializer(read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "incident",
            "channel",
            "status",
            "attempts",
            "sent_at",
            "read_at",
            "created_at",
        ]
        read_only_fields = fields


class CountSerializer(serializers.Serializer):
    count = serializers.IntegerField()
