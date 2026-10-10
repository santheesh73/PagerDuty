import uuid
from dataclasses import asdict

from django.db.models import Count, Q, QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from apps.alerting.actions import Event, ingest
from apps.core.permissions import IsTeamMember, Role
from apps.core.views import actor, require_role, scope_to_teams
from apps.incidents.models import Status

from . import actions
from .models import Service
from .serializers import ServiceModeSerializer, ServiceSerializer, TestAlertResultSerializer

OPEN = ~Q(incidents__status=Status.RESOLVED)


class ServiceViewSet(viewsets.ModelViewSet):
    serializer_class = ServiceSerializer
    permission_classes = [IsTeamMember]
    filterset_fields = ["team", "mode", "escalation_policy"]

    def get_queryset(self) -> QuerySet[Service]:
        return scope_to_teams(
            Service.objects.select_related("escalation_policy").annotate(
                open_high=Count("incidents", filter=OPEN & Q(incidents__urgency="high")),
                open_low=Count("incidents", filter=OPEN & Q(incidents__urgency="low")),
            ),
            self.request.user,
        ).order_by("name")

    def perform_create(self, serializer: BaseSerializer) -> None:
        require_role(self.request.user, serializer.validated_data["team"].pk, Role.ADMIN)
        serializer.save()

    def _fresh(self, service: Service) -> Response:
        return Response(self.get_serializer(self.get_queryset().get(pk=service.pk)).data)

    @extend_schema(request=None, responses=ServiceSerializer)
    @action(detail=True, methods=["post"], url_path="rotate-key")
    def rotate_key(self, request: Request, pk: str | None = None) -> Response:
        service = self.get_object()  # IsTeamMember: POST requires team admin
        actions.rotate_integration_key(service)
        return self._fresh(service)

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
