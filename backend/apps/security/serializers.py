from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.core.demo import guarding

from .models import AuditEvent, SessionRecord


class MfaCodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=32, trim_whitespace=True)


class MfaStatusSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    enforced = serializers.BooleanField(
        help_text="True if your role requires MFA (team admins and staff)."
    )
    backup_codes_remaining = serializers.IntegerField()


class MfaSetupSerializer(serializers.Serializer):
    secret = serializers.CharField(
        help_text="Base32. Shown once; type it into an authenticator app."
    )
    otpauth_uri = serializers.CharField()


class BackupCodesSerializer(serializers.Serializer):
    backup_codes = serializers.ListField(child=serializers.CharField(), help_text="Shown once.")


class DisableMfaSerializer(serializers.Serializer):
    password = serializers.CharField(trim_whitespace=False)
    code = serializers.CharField(max_length=32)


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False, max_length=256)

    def validate(self, attrs: dict) -> dict:
        user = self.context["user"]
        if not user.check_password(attrs["current_password"]):
            raise serializers.ValidationError(
                {"current_password": "That is not your current password."}
            )
        validate_password(attrs["new_password"], user)
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=64)
    token = serializers.CharField(max_length=128)
    new_password = serializers.CharField(trim_whitespace=False, max_length=256)


class SessionSerializer(serializers.ModelSerializer):
    current = serializers.SerializerMethodField()

    class Meta:
        model = SessionRecord
        fields = ["id", "created_at", "ip", "user_agent", "current"]
        read_only_fields = fields

    def get_current(self, obj: SessionRecord) -> bool:
        request = self.context.get("request")
        return bool(request and request.session.session_key == obj.session_key)

    def to_representation(self, instance: SessionRecord) -> dict:
        data = super().to_representation(instance)
        if guarding(getattr(self.context.get("request"), "user", None)):
            data["ip"], data["user_agent"] = None, ""  # other visitors' addresses, see core/demo.py
        return data


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "created_at",
            "action",
            "actor_id",
            "actor_email",
            "team_id",
            "target_type",
            "target_id",
            "ip",
            "data",
        ]
        read_only_fields = fields

    def to_representation(self, instance: AuditEvent) -> dict:
        data = super().to_representation(instance)
        if guarding(getattr(self.context.get("request"), "user", None)):
            data["ip"] = None
        return data


class RevokedCountSerializer(serializers.Serializer):
    count = serializers.IntegerField()
