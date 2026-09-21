from rest_framework import serializers

from apps.services.models import Service
from apps.services.serializers import ServiceSummarySerializer

from .models import Alert


class AlertSerializer(serializers.ModelSerializer):
    """Output representation of a persisted operational alert."""

    service = ServiceSummarySerializer(read_only=True)
    incident_id = serializers.IntegerField(source="incident.id", read_only=True, allow_null=True)

    class Meta:
        model = Alert
        fields = [
            "id",
            "service",
            "severity",
            "message",
            "source",
            "fingerprint",
            "metadata",
            "received_at",
            "created_at",
            "incident_id",
        ]
        read_only_fields = [
            "id",
            "fingerprint",
            "received_at",
            "created_at",
            "incident_id",
        ]


class AlertIngestSerializer(serializers.Serializer):
    """
    Dedicated deserializer for alert ingestion payloads (POST /api/alerts/).
    Encapsulates strict domain validation before forwarding to ingest_alert().
    """

    service_id = serializers.PrimaryKeyRelatedField(
        queryset=Service.objects.all(),
        source="service",
        error_messages={
            "does_not_exist": "Service does not exist.",
            "incorrect_type": "Incorrect type. Expected service ID value.",
        },
    )
    severity = serializers.CharField(max_length=32)
    message = serializers.CharField()
    source = serializers.CharField(max_length=64)
    metadata = serializers.DictField(required=False, default=dict)

    def validate_message(self, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise serializers.ValidationError("Alert message cannot be blank.")
        return trimmed

    def validate_source(self, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise serializers.ValidationError("Alert source cannot be blank.")
        return trimmed

    def validate_severity(self, value: str) -> str:
        canonical = value.strip().upper()
        if canonical not in Alert.Severity.values:
            valid_choices = ", ".join(Alert.Severity.values)
            raise serializers.ValidationError(
                f"Invalid severity '{value}'. Must be one of: {valid_choices}."
            )
        return canonical

    def validate_service_id(self, service: Service) -> Service:
        if not service.is_active:
            raise serializers.ValidationError("Cannot ingest alert for inactive service.")
        return service
