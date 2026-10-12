from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from apps.core.pagination import CursorPagination
from apps.core.params import choices_param, datetime_param, int_param
from apps.core.permissions import CanRespond, Role, has_role
from apps.core.views import actor, require_role

from . import actions
from .models import Incident, Status, Urgency
from .selectors import filter_incidents, timeline, visible_incidents
from .serializers import (
    AlertSerializer,
    DeliverySerializer,
    IncidentDetailSerializer,
    IncidentEventSerializer,
    IncidentSerializer,
    NoteSerializer,
    ReassignSerializer,
)


class IncidentCursorPagination(CursorPagination):
    # The id breaks ties: incidents opened in the same instant (an alert storm) otherwise come
    # back in no fixed order, and a cursor over an unstable order skips and repeats rows.
    ordering = ("-triggered_at", "-id")


class TimelineCursorPagination(CursorPagination):
    page_size = 100
    ordering = ("-created_at", "-id")


class AlertCursorPagination(CursorPagination):
    ordering = ("-received_at", "-id")


LIST_PARAMS = [
    OpenApiParameter("status", str, description="Comma-separated: triggered,acknowledged,resolved"),
    OpenApiParameter("urgency", str, enum=["high", "low"]),
    OpenApiParameter("service", int),
    OpenApiParameter("team", int),
    OpenApiParameter("assignee", str, description="A user id, or `me`"),
    OpenApiParameter("since", str, description="ISO-8601; triggered at or after"),
    OpenApiParameter("until", str, description="ISO-8601; triggered before"),
    OpenApiParameter("search", str, description="Title text, #number or exact dedup key"),
]


class IncidentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [CanRespond]
    pagination_class = IncidentCursorPagination

    def get_queryset(self) -> QuerySet[Incident]:
        return visible_incidents(self.request.user)

    def get_serializer_class(self) -> type[BaseSerializer]:
        return IncidentDetailSerializer if self.action != "list" else IncidentSerializer

    @extend_schema(parameters=LIST_PARAMS)
    def list(self, request: Request, *args: object, **kwargs: object) -> Response:
        params = request.query_params
        assignee = params.get("assignee") or None
        if assignee not in (None, "me"):
            int_param(params, "assignee")  # a user id, or `me`
        incidents = filter_incidents(
            self.get_queryset(),
            user=actor(request),
            status=choices_param(params, "status", set(Status.values)),
            urgency=choices_param(params, "urgency", set(Urgency.values)),
            service=int_param(params, "service"),
            team=int_param(params, "team"),
            assignee=assignee,
            since=datetime_param(params, "since"),
            until=datetime_param(params, "until"),
            search=params.get("search"),
        )
        page = self.paginate_queryset(incidents)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    def _respond(self, incident: Incident) -> Response:
        fresh = self.get_queryset().get(pk=incident.pk)
        return Response(IncidentDetailSerializer(fresh, context={"request": self.request}).data)

    @extend_schema(request=None, responses=IncidentDetailSerializer)
    @action(detail=True, methods=["post"])
    def acknowledge(self, request: Request, pk: str | None = None) -> Response:
        return self._respond(actions.acknowledge(self.get_object().pk, actor=actor(request)))

    @extend_schema(request=None, responses=IncidentDetailSerializer)
    @action(detail=True, methods=["post"])
    def unacknowledge(self, request: Request, pk: str | None = None) -> Response:
        return self._respond(actions.unacknowledge(self.get_object().pk, actor=actor(request)))

    @extend_schema(request=None, responses=IncidentDetailSerializer)
    @action(detail=True, methods=["post"])
    def resolve(self, request: Request, pk: str | None = None) -> Response:
        return self._respond(actions.resolve(self.get_object().pk, actor=actor(request)))

    @extend_schema(request=None, responses=IncidentDetailSerializer)
    @action(detail=True, methods=["post"])
    def escalate(self, request: Request, pk: str | None = None) -> Response:
        return self._respond(actions.escalate(self.get_object().pk, actor=actor(request)))

    @extend_schema(request=ReassignSerializer, responses=IncidentDetailSerializer)
    @action(detail=True, methods=["post"])
    def reassign(self, request: Request, pk: str | None = None) -> Response:
        incident = self.get_object()
        payload = ReassignSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        assignee = payload.validated_data["assignee"]
        if not has_role(assignee, incident.service.team_id, Role.RESPONDER):
            raise ValidationError({"assignee": "Must be a responder or admin on this team."})
        return self._respond(actions.reassign(incident.pk, actor=actor(request), assignee=assignee))

    @extend_schema(request=NoteSerializer, responses={201: IncidentEventSerializer})
    @action(detail=True, methods=["post"])
    def notes(self, request: Request, pk: str | None = None) -> Response:
        incident = self.get_object()
        payload = NoteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        event = actions.add_note(
            incident.pk, actor=actor(request), text=payload.validated_data["text"]
        )
        return Response(IncidentEventSerializer(event).data, status=201)

    @extend_schema(responses=IncidentEventSerializer(many=True))
    @action(detail=True, methods=["get"], pagination_class=TimelineCursorPagination)
    def timeline(self, request: Request, pk: str | None = None) -> Response:
        page = self.paginate_queryset(timeline(self.get_object()))
        return self.get_paginated_response(IncidentEventSerializer(page, many=True).data)

    @extend_schema(responses=DeliverySerializer(many=True))
    @action(detail=True, methods=["get"], pagination_class=None)
    def notifications(self, request: Request, pk: str | None = None) -> Response:
        """How each page of this incident was delivered, and the error when one failed."""
        incident = self.get_object()
        require_role(request.user, incident.service.team_id, Role.RESPONDER)
        rows = incident.notifications.select_related("user").order_by("created_at", "id")[:200]
        return Response(DeliverySerializer(rows, many=True).data)

    @extend_schema(responses=AlertSerializer(many=True))
    @action(detail=True, methods=["get"], pagination_class=AlertCursorPagination)
    def alerts(self, request: Request, pk: str | None = None) -> Response:
        page = self.paginate_queryset(self.get_object().alerts.all())
        return self.get_paginated_response(AlertSerializer(page, many=True).data)
