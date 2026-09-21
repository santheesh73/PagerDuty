from django.db.models import Count
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .exceptions import IncidentDomainError, IncidentReopenConflict, IncidentStateConflict
from .models import Incident
from .serializers import IncidentEventSerializer, IncidentSerializer
from .services import acknowledge_incident, reopen_incident, resolve_incident


class IncidentViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
):
    """
    API endpoints for inspecting operational incidents and driving state machine transitions.
    Normal creation occurs strictly via alert triage (POST /api/alerts/).
    Arbitrary updates and deletes are prohibited to preserve audit trail integrity.
    """

    queryset = (
        Incident.objects.select_related("service", "assigned_user")
        .annotate(alert_count=Count("alerts"))
        .all()
        .order_by("-triggered_at")
    )
    serializer_class = IncidentSerializer
    permission_classes = [AllowAny]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()

        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status__iexact=status_param.strip())

        service_param = self.request.query_params.get("service")
        if service_param:
            qs = qs.filter(service_id=service_param)

        severity_param = self.request.query_params.get("severity")
        if severity_param:
            qs = qs.filter(severity__iexact=severity_param.strip())

        active_param = self.request.query_params.get("active")
        if active_param is not None:
            is_active = active_param.strip().lower() in ["true", "1", "yes"]
            qs = qs.filter(resolved_at__isnull=is_active)

        return qs

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        """
        Transitions incident from TRIGGERED to ACKNOWLEDGED.
        Idempotent if already acknowledged.
        Returns 409 Conflict if incident is already resolved.
        """
        incident = self.get_object()
        actor = request.user if getattr(request.user, "is_authenticated", False) else None
        try:
            updated_incident = acknowledge_incident(incident=incident, user=actor)
        except IncidentStateConflict as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        # Refresh alert_count for serialized output
        updated_incident.alert_count = incident.alerts.count()
        return Response(IncidentSerializer(updated_incident).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        """
        Transitions incident to RESOLVED.
        Allowed from TRIGGERED or ACKNOWLEDGED.
        Idempotent if already resolved.
        """
        incident = self.get_object()
        actor = request.user if getattr(request.user, "is_authenticated", False) else None
        try:
            updated_incident = resolve_incident(incident=incident, user=actor)
        except IncidentDomainError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        updated_incident.alert_count = incident.alerts.count()
        return Response(IncidentSerializer(updated_incident).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        """
        Transitions a RESOLVED incident back to TRIGGERED.
        Returns 409 Conflict if incident is not resolved, or if an active incident
        already exists for the same service and fingerprint.
        """
        incident = self.get_object()
        actor = request.user if getattr(request.user, "is_authenticated", False) else None
        try:
            updated_incident = reopen_incident(incident=incident, user=actor)
        except (IncidentStateConflict, IncidentReopenConflict) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        updated_incident.alert_count = incident.alerts.count()
        return Response(IncidentSerializer(updated_incident).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def events(self, request, pk=None):
        """
        Returns the immutable chronological timeline of events for this incident.
        Ordered strictly by created_at ASC, id ASC. Read-only.
        """
        incident = self.get_object()
        events = (
            incident.events.select_related("actor")
            .all()
            .order_by("created_at", "id")
        )
        return Response(
            IncidentEventSerializer(events, many=True).data,
            status=status.HTTP_200_OK,
        )
