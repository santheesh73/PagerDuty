from rest_framework import serializers

from .models import Severity


class EventPayloadSerializer(serializers.Serializer):
    summary = serializers.CharField(max_length=1024)
    severity = serializers.ChoiceField(choices=Severity.choices)
    source = serializers.CharField(max_length=255)  # type: ignore[assignment]
    custom_details = serializers.JSONField(required=False, default=dict)


class EventSerializer(serializers.Serializer):
    routing_key = serializers.CharField(max_length=64)
    event_action = serializers.ChoiceField(choices=["trigger", "acknowledge", "resolve"])
    dedup_key = serializers.CharField(max_length=255, required=False, allow_blank=True)
    payload = EventPayloadSerializer(required=False)

    def validate(self, attrs: dict) -> dict:
        if attrs["event_action"] == "trigger" and "payload" not in attrs:
            raise serializers.ValidationError({"payload": "Required for trigger events."})
        if attrs["event_action"] != "trigger" and not attrs.get("dedup_key"):
            raise serializers.ValidationError({"dedup_key": "Required to acknowledge or resolve."})
        return attrs


class EventResultSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["accepted", "ignored"])
    dedup_key = serializers.CharField()
    incident_id = serializers.IntegerField(allow_null=True)
