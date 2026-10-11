import math
from typing import Any

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import Team
from apps.core import limits
from apps.core.permissions import Role, has_role
from apps.escalations.models import EscalationPolicy

from .models import Service


class OpenCountsSerializer(serializers.Serializer):
    high = serializers.IntegerField()
    low = serializers.IntegerField()


class ServiceSerializer(serializers.ModelSerializer):
    team = serializers.PrimaryKeyRelatedField(queryset=Team.objects.all())
    escalation_policy = serializers.PrimaryKeyRelatedField(queryset=EscalationPolicy.objects.all())
    escalation_policy_name = serializers.CharField(source="escalation_policy.name", read_only=True)
    integration_key = serializers.SerializerMethodField(
        help_text="The full key, returned exactly once: in the response that created or rotated "
        "it (to a team admin). Null everywhere else: only a hash is stored."
    )
    integration_key_prefix = serializers.SerializerMethodField(
        help_text="First 8 characters of the current key, to recognise it. Team admins only."
    )
    open_incidents = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = [
            "id",
            "team",
            "name",
            "description",
            "escalation_policy",
            "escalation_policy_name",
            "integration_key",
            "integration_key_prefix",
            "previous_key_expires_at",
            "mode",
            "mode_until",
            "open_incidents",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "mode",
            "mode_until",
            "previous_key_expires_at",
            "created_at",
            "updated_at",
        ]

    def _is_admin(self, obj: Service) -> bool:
        request = self.context.get("request")
        return bool(request and has_role(request.user, obj.team_id, Role.ADMIN))

    def get_integration_key(self, obj: Service) -> str | None:
        issued = self.context.get("issued_key") or getattr(obj, "integration_key", None)
        return issued if issued and self._is_admin(obj) else None

    def get_integration_key_prefix(self, obj: Service) -> str | None:
        return obj.integration_key_prefix if self._is_admin(obj) else None

    @extend_schema_field(OpenCountsSerializer)
    def get_open_incidents(self, obj: Service) -> dict[str, int]:
        return {"high": getattr(obj, "open_high", 0), "low": getattr(obj, "open_low", 0)}

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        team = attrs.get("team") or getattr(self.instance, "team", None)
        policy = attrs.get("escalation_policy") or getattr(self.instance, "escalation_policy", None)
        if policy is not None and team is not None and policy.team_id != team.pk:
            raise serializers.ValidationError(
                {"escalation_policy": "The policy must belong to the service's team."}
            )
        if self.instance is not None and "team" in attrs and attrs["team"] != self.instance.team:
            raise serializers.ValidationError({"team": "A service cannot move between teams."})
        return attrs


class ServiceModeSerializer(serializers.Serializer):
    """Maintenance and debug suppress paging, so both need a bounded window.

    Without one, a service quietly stops paging for good and nobody finds out until an
    outage goes unanswered. `expire_service_modes` only reclaims services that have a
    `mode_until`, so an open-ended window would never be swept back to active.
    """

    mode = serializers.ChoiceField(choices=Service.Mode.choices)
    until = serializers.DateTimeField(required=False, allow_null=True)

    def validate_until(self, value: Any) -> Any:
        if value is not None and value <= timezone.now():
            raise serializers.ValidationError("Must be in the future.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["mode"] == Service.Mode.ACTIVE:
            return attrs
        until = attrs.get("until")
        if until is None:
            raise serializers.ValidationError(
                {"until": f"Required for {attrs['mode']} mode, which suppresses paging."}
            )
        hours = (until - timezone.now()).total_seconds() / 3600
        limits.enforce("mode_window_hours", math.ceil(hours))
        return attrs


class TestAlertResultSerializer(serializers.Serializer):
    status = serializers.CharField()
    dedup_key = serializers.CharField()
    incident_id = serializers.IntegerField(allow_null=True)
    created = serializers.BooleanField()
