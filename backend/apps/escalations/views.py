from typing import Any

from django.db.models import QuerySet
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView

from apps.accounts.serializers import UserSummarySerializer
from apps.core.permissions import IsTeamMember, Role
from apps.core.views import require_role, scope_to_teams
from apps.security.audit import AuditedMixin

from .models import EscalationPolicy
from .selectors import oncall_overview, policies_with_rules
from .serializers import EscalationPolicySerializer


class EscalationPolicyViewSet(AuditedMixin, viewsets.ModelViewSet):
    audit_name = "escalation_policy"

    serializer_class = EscalationPolicySerializer
    permission_classes = [IsTeamMember]
    filterset_fields = ["team"]

    def get_queryset(self) -> QuerySet[EscalationPolicy]:
        return scope_to_teams(policies_with_rules(), self.request.user).order_by("name")

    def perform_create(self, serializer: BaseSerializer) -> None:
        require_role(self.request.user, serializer.validated_data["team"].pk, Role.ADMIN)
        serializer.save()


class ScheduleRefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class OnCallEntrySerializer(serializers.Serializer):
    user = UserSummarySerializer(allow_null=True)
    schedule = ScheduleRefSerializer(allow_null=True)


class OnCallLevelSerializer(serializers.Serializer):
    level = serializers.IntegerField()
    delay_minutes = serializers.IntegerField()
    oncall = OnCallEntrySerializer(many=True)


class PolicyRefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    team = serializers.IntegerField(source="team_id")


class OnCallPolicySerializer(serializers.Serializer):
    policy = PolicyRefSerializer()
    levels = OnCallLevelSerializer(many=True)


class OnCallsView(APIView):
    """Who would be paged right now, for every level of every policy you can see."""

    @extend_schema(responses=OnCallPolicySerializer(many=True))
    def get(self, request: Request) -> Response:
        policies = scope_to_teams(EscalationPolicy.objects.all(), request.user)
        data: list[dict[str, Any]] = oncall_overview(policies, timezone.now())
        return Response(OnCallPolicySerializer(data, many=True).data)
