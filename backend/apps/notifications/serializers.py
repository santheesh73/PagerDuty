import re
from urllib.parse import urlsplit

from django.conf import settings
from rest_framework import serializers

from apps.core import safe_http

from . import providers
from .models import Notification, NotificationRule, UserContact


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


# --- contact details and personal rules ---------------------------------------------------------


E164 = re.compile(r"^\+[1-9]\d{6,14}$")


class ContactSerializer(serializers.Serializer):
    """What the API says about a person's contact details. Secrets are write-only: the webhook
    URL (often itself a secret) is reduced to its host, and the signing key is never returned
    here (only once, when it is created)."""

    phone_number = serializers.CharField()
    phone_verified = serializers.BooleanField()
    webhook_host = serializers.CharField()
    has_webhook = serializers.BooleanField()
    sms_voice_available = serializers.BooleanField()

    @staticmethod
    def of(contact: UserContact | None) -> dict:
        return {
            "phone_number": contact.phone_number if contact else "",
            "phone_verified": bool(contact and contact.phone_verified),
            "webhook_host": (urlsplit(contact.webhook_url).hostname or "") if contact else "",
            "has_webhook": bool(contact and contact.webhook_url),
            "sms_voice_available": providers.configured(),
        }


class ContactUpdateSerializer(serializers.Serializer):
    phone_number = serializers.CharField(required=False, allow_blank=True, max_length=20)
    webhook_url = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate_phone_number(self, value: str) -> str:
        value = value.strip().replace(" ", "")
        if value and not E164.match(value):
            raise serializers.ValidationError(
                "Use international format: a + sign, country code and number, e.g. +14155550123."
            )
        return value

    def validate_webhook_url(self, value: str) -> str:
        value = value.strip()
        if value:
            try:
                safe_http.validate_url(value, allow_private=settings.WEBHOOK_ALLOW_PRIVATE)
            except safe_http.UnsafeURL as exc:
                raise serializers.ValidationError(str(exc)) from exc
        return value


class SecretResponseSerializer(serializers.Serializer):
    webhook_secret = serializers.CharField()


class ContactUpdateResponseSerializer(ContactSerializer):
    webhook_secret = serializers.CharField(
        required=False, help_text="Shown once, when a webhook URL is set or rotated."
    )


class CodeSerializer(serializers.Serializer):
    code = serializers.RegexField(r"^\d{6}$")


class NotificationRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationRule
        fields = ["id", "position", "channel", "delay_minutes", "urgency", "enabled"]
        read_only_fields = ["id", "position"]
        extra_kwargs = {"delay_minutes": {"max_value": 1440}}
