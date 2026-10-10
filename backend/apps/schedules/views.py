from datetime import UTC, datetime, timedelta

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from apps.accounts.models import User
from apps.core.permissions import IsTeamMember, Role
from apps.core.views import require_role, scope_to_teams

from .models import Schedule, ScheduleOverride
from .oncall import on_call_with_source
from .selectors import load_schedule_spec, schedules_with_layers, shifts_for
from .serializers import (
    OnCallNowSerializer,
    OverrideSerializer,
    ScheduleSerializer,
    ShiftSerializer,
)

MAX_SHIFT_WINDOW = timedelta(days=62)


def _parse_instant(request: Request, name: str, default: datetime) -> datetime:
    raw = request.query_params.get(name)
    if not raw:
        return default
    value = parse_datetime(raw)
    if value is None:
        raise ValidationError({name: "Expected an ISO-8601 datetime."})
    return value if timezone.is_aware(value) else timezone.make_aware(value, UTC)


class ScheduleViewSet(viewsets.ModelViewSet):
    serializer_class = ScheduleSerializer
    permission_classes = [IsTeamMember]
    filterset_fields = ["team"]

    def get_queryset(self) -> QuerySet[Schedule]:
        return scope_to_teams(schedules_with_layers(), self.request.user).order_by("name")

    def perform_create(self, serializer: BaseSerializer) -> None:
        require_role(self.request.user, serializer.validated_data["team"].pk, Role.ADMIN)
        serializer.save()

    @extend_schema(
        parameters=[OpenApiParameter("at", datetime, description="Defaults to now")],
        responses=OnCallNowSerializer,
    )
    @action(detail=True, methods=["get"])
    def oncall(self, request: Request, pk: str | None = None) -> Response:
        schedule = self.get_object()
        at = _parse_instant(request, "at", timezone.now())
        user_id, source = on_call_with_source(load_schedule_spec(schedule, since=at), at)
        user = User.objects.filter(pk=user_id).first() if user_id else None
        return Response(OnCallNowSerializer({"at": at, "user": user, "source": source}).data)

    @extend_schema(
        parameters=[
            OpenApiParameter("since", datetime, description="Defaults to now"),
            OpenApiParameter("until", datetime, description="Defaults to since + 7 days"),
        ],
        responses=ShiftSerializer(many=True),
    )
    @action(detail=True, methods=["get"], pagination_class=None)
    def shifts(self, request: Request, pk: str | None = None) -> Response:
        schedule = self.get_object()
        since = _parse_instant(request, "since", timezone.now())
        until = _parse_instant(request, "until", since + timedelta(days=7))
        if until <= since or until - since > MAX_SHIFT_WINDOW:
            raise ValidationError({"until": "Window must be positive and at most 62 days."})
        shifts = shifts_for(schedule, since, until)
        users = User.objects.in_bulk({s.user_id for s in shifts})
        rows = [
            {"user": users[s.user_id], "start": s.start, "end": s.end, "source": s.source}
            for s in shifts
            if s.user_id in users
        ]
        return Response(ShiftSerializer(rows, many=True).data)


class OverrideViewSet(viewsets.ModelViewSet):
    """/schedules/{schedule_pk}/overrides/ — members read, team admins write."""

    serializer_class = OverrideSerializer
    permission_classes = [IsTeamMember]
    pagination_class = None

    def get_schedule(self) -> Schedule:
        schedule = get_object_or_404(Schedule, pk=self.kwargs["schedule_pk"])
        require_role(self.request.user, schedule.team_id, Role.VIEWER)
        return schedule

    def get_queryset(self) -> QuerySet[ScheduleOverride]:
        if getattr(self, "swagger_fake_view", False):  # OpenAPI generation
            return ScheduleOverride.objects.none()
        overrides = ScheduleOverride.objects.filter(schedule=self.get_schedule())
        if since := self.request.query_params.get("since"):
            overrides = overrides.filter(end__gt=since)
        return overrides.select_related("user").order_by("start")

    def get_serializer_context(self) -> dict:
        context = super().get_serializer_context()
        if "schedule_pk" in self.kwargs and not getattr(self, "swagger_fake_view", False):
            context["schedule"] = self.get_schedule()
        return context

    def perform_create(self, serializer: BaseSerializer) -> None:
        schedule = self.get_schedule()
        require_role(self.request.user, schedule.team_id, Role.ADMIN)
        serializer.save(schedule=schedule)
