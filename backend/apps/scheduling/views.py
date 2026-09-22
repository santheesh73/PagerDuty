from datetime import datetime

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Schedule, ScheduleRotation
from .serializers import ScheduleRotationSerializer, ScheduleSerializer
from .services import get_on_call_assignment


class ScheduleViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing operational on-call Schedules.
    Supports filtering by team, is_active, and is_primary.
    Provides /api/schedules/{id}/on-call/?at=... endpoint.
    """

    queryset = Schedule.objects.select_related("team").all().order_by("name")
    serializer_class = ScheduleSerializer
    permission_classes = [AllowAny]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()

        team_param = self.request.query_params.get("team")
        if team_param:
            qs = qs.filter(team_id=team_param)

        is_active_param = self.request.query_params.get("is_active")
        if is_active_param is not None:
            is_active = is_active_param.lower() in ("true", "1")
            qs = qs.filter(is_active=is_active)

        is_primary_param = self.request.query_params.get("is_primary")
        if is_primary_param is not None:
            is_primary = is_primary_param.lower() in ("true", "1")
            qs = qs.filter(is_primary=is_primary)

        return qs

    @action(detail=True, methods=["get"], url_path="on-call")
    def on_call(self, request, pk=None):
        schedule = self.get_object()
        at_param = request.query_params.get("at")

        if at_param:
            clean_at = at_param.strip()
            if " " in clean_at and "+" not in clean_at:
                clean_at = clean_at.replace(" ", "+")
            parsed_dt = parse_datetime(clean_at)
            if parsed_dt is None:
                try:
                    parsed_dt = datetime.fromisoformat(clean_at.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    return Response(
                        {"detail": f"Invalid ISO 8601 datetime '{at_param}'."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            if timezone.is_naive(parsed_dt):
                return Response(
                    {"detail": "Timestamp must be timezone-aware (e.g. 2026-09-21T10:00:00Z)."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            target_time = parsed_dt
        else:
            target_time = timezone.now()

        assignment = get_on_call_assignment(schedule, target_time)

        user_data = None
        source_data = None
        if assignment:
            user = assignment["user"]
            user_data = {
                "id": user.id,
                "username": user.username,
                "name": user.get_full_name().strip() or user.username,
            }
            source_data = assignment["source"]

        return Response(
            {
                "schedule_id": schedule.id,
                "at": target_time.isoformat(),
                "user": user_data,
                "source": source_data,
            },
            status=status.HTTP_200_OK,
        )


class ScheduleRotationViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing concrete ScheduleRotations (shifts and overrides).
    Supports filtering by schedule, user, and is_override.
    """

    queryset = (
        ScheduleRotation.objects.select_related("schedule", "user", "schedule__team")
        .all()
        .order_by("start_time", "id")
    )
    serializer_class = ScheduleRotationSerializer
    permission_classes = [AllowAny]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()

        schedule_param = self.request.query_params.get("schedule")
        if schedule_param:
            qs = qs.filter(schedule_id=schedule_param)

        user_param = self.request.query_params.get("user")
        if user_param:
            qs = qs.filter(user_id=user_param)

        is_override_param = self.request.query_params.get("is_override")
        if is_override_param is not None:
            is_override = is_override_param.lower() in ("true", "1")
            qs = qs.filter(is_override=is_override)

        return qs
