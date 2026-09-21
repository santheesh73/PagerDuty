from django.db import transaction
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer
from .tasks import dispatch_notification


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only operational API for inspecting dispatched notifications.
    Ordinary clients cannot POST arbitrary notification records.
    Supports filtering by incident, recipient, status, and channel.
    """

    queryset = (
        Notification.objects.select_related("incident", "recipient", "escalation_level")
        .all()
        .order_by("-created_at")
    )
    serializer_class = NotificationSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = super().get_queryset()

        incident_param = self.request.query_params.get("incident")
        if incident_param:
            qs = qs.filter(incident_id=incident_param)

        recipient_param = self.request.query_params.get("recipient")
        if recipient_param:
            qs = qs.filter(recipient_id=recipient_param)

        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param.strip().upper())

        channel_param = self.request.query_params.get("channel")
        if channel_param:
            qs = qs.filter(channel=channel_param.strip().upper())

        return qs

    @action(detail=True, methods=["post"], url_path="retry")
    def retry(self, request, pk=None):
        """
        Manually triggers a retry for a FAILED notification.
        Re-enqueues the existing notification; does NOT create duplicate records.
        """
        notification = self.get_object()
        if notification.status != Notification.Status.FAILED:
            return Response(
                {"detail": f"Only FAILED notifications can be manually retried (current status: {notification.status})."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            notification.status = Notification.Status.PENDING
            notification.save(update_fields=["status", "updated_at"])
            transaction.on_commit(lambda: dispatch_notification.delay(notification.id))

        return Response(
            {"detail": "Notification retry enqueued successfully.", "id": notification.id},
            status=status.HTTP_200_OK,
        )
