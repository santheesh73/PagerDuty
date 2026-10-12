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

    def validate_dedup_key(self, value: str) -> str:
        # The key Pulse itself uses to group a service's maintenance-mode alerts: a monitor
        # naming it would have a paging incident absorb them (and maintenance never close it).
        if value == "__maintenance__":
            raise serializers.ValidationError("This dedup key is reserved.")
        return value

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
