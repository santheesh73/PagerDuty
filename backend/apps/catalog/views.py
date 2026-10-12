import uuid
from dataclasses import asdict
from typing import Any

from django.db.models import Count, Q, QuerySet
from django_filters import ChoiceFilter, FilterSet
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from apps.accounts.models import Team
from apps.alerting.actions import Event, ingest
from apps.core.permissions import IsTeamMember, Role
from apps.core.scoping import scoped_choice_filter
from apps.core.views import actor, no_store, require_role, scope_to_teams
from apps.escalations.models import EscalationPolicy
from apps.incidents.models import Status
from apps.security import audit
from apps.security.audit import AuditedMixin

from . import actions
from .models import Service
from .serializers import ServiceModeSerializer, ServiceSerializer, TestAlertResultSerializer

OPEN = ~Q(incidents__status=Status.RESOLVED)


class ServiceFilter(FilterSet):
    team = scoped_choice_filter(Team, "id")
    escalation_policy = scoped_choice_filter(EscalationPolicy, "team_id")
    mode = ChoiceFilter(choices=Service.Mode.choices)

    class Meta:
        model = Service
        fields = ["team", "mode", "escalation_policy"]


class ServiceViewSet(AuditedMixin, viewsets.ModelViewSet):
    audit_name = "service"

    serializer_class = ServiceSerializer
    permission_classes = [IsTeamMember]
    filterset_class = ServiceFilter

    def get_queryset(self) -> QuerySet[Service]:
        return scope_to_teams(
            Service.objects.select_related("escalation_policy").annotate(
                open_high=Count("incidents", filter=OPEN & Q(incidents__urgency="high")),
                open_low=Count("incidents", filter=OPEN & Q(incidents__urgency="low")),
            ),
            self.request.user,
        ).order_by("name", "id")

    def perform_create(self, serializer: BaseSerializer) -> None:
        require_role(self.request.user, serializer.validated_data["team"].pk, Role.ADMIN)
        serializer.save()

    def finalize_response(
        self, request: Request, response: Response, *args: Any, **kwargs: Any
    ) -> Response:
        response = super().finalize_response(request, response, *args, **kwargs)
        # A freshly issued integration key (create, rotate) is shown exactly once.
        if isinstance(response.data, dict) and response.data.get("integration_key"):
            no_store(response)
        return response

    def _fresh(self, service: Service, *, issued_key: str | None = None) -> Response:
        context = {**self.get_serializer_context(), "issued_key": issued_key}
        fresh = self.get_queryset().get(pk=service.pk)
        return Response(self.get_serializer_class()(fresh, context=context).data)

    @extend_schema(request=None, responses=ServiceSerializer)
    @action(detail=True, methods=["post"], url_path="rotate-key")
    def rotate_key(self, request: Request, pk: str | None = None) -> Response:
        service = self.get_object()  # IsTeamMember: POST requires team admin
        key = actions.rotate_integration_key(service)
        audit.record("service.key_rotated", request=request, target=service)
        return self._fresh(service, issued_key=key)

    @extend_schema(request=ServiceModeSerializer, responses=ServiceSerializer)
    @action(detail=True, methods=["post"])
    def mode(self, request: Request, pk: str | None = None) -> Response:
        service = self.get_object()
        payload = ServiceModeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        actions.set_mode(
            service,
            payload.validated_data["mode"],
            until=payload.validated_data.get("until"),
            actor=actor(request),
        )
        return self._fresh(service)

    @extend_schema(request=None, responses={202: TestAlertResultSerializer})
    @action(
        detail=True, methods=["post"], url_path="test-alert", permission_classes=[IsAuthenticated]
    )  # responders may send one: checked below
    def test_alert(self, request: Request, pk: str | None = None) -> Response:
        service = self.get_object()
        require_role(request.user, service.team_id, Role.RESPONDER)
        result = ingest(
            service,
            Event(
                action="trigger",
                dedup_key=f"test-{uuid.uuid4().hex[:12]}",
                summary=f"Test alert for {service.name} (sent by {request.user})",
                severity="critical",
                source="pulse test alert",
            ),
        )
        return Response(TestAlertResultSerializer(asdict(result)).data, status=202)
