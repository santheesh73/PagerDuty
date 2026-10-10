from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.views import actor

from . import actions
from .models import Notification
from .serializers import CountSerializer, NotificationSerializer


class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Your in-app inbox. Only in-app rows: email copies are delivery records, not inbox items."""

    serializer_class = NotificationSerializer

    def get_queryset(self) -> QuerySet[Notification]:
        if getattr(self, "swagger_fake_view", False):  # OpenAPI generation
            return Notification.objects.none()
        rows = Notification.objects.filter(
            user=actor(self.request), channel=Notification.Channel.IN_APP
        ).select_related("incident")
        if self.request.query_params.get("unread") in {"1", "true"}:
            rows = rows.filter(read_at__isnull=True)
        return rows.order_by("-created_at", "-id")

    @extend_schema(parameters=[OpenApiParameter("unread", bool)])
    def list(self, request: Request, *args: object, **kwargs: object) -> Response:
        return super().list(request, *args, **kwargs)

    @extend_schema(request=None, responses=NotificationSerializer)
    @action(detail=True, methods=["post"])
    def read(self, request: Request, pk: str | None = None) -> Response:
        return Response(NotificationSerializer(actions.mark_read(self.get_object())).data)

    @extend_schema(request=None, responses=CountSerializer)
    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request: Request) -> Response:
        return Response({"count": actions.mark_all_read(actor(request))})

    @extend_schema(responses=CountSerializer)
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request: Request) -> Response:
        count = self.get_queryset().filter(read_at__isnull=True).count()
        return Response({"count": count})
