from rest_framework import mixins, status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Alert
from .serializers import AlertIngestSerializer, AlertSerializer
from .services import ingest_alert


class AlertViewSet(
    viewsets.GenericViewSet,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
):
    """
    API endpoint for Alert ingestion and inspection.
    POST: Ingests an operational alert, assigns fingerprint, and persists.
    GET: Inspects alerts with filtering by service, severity, and source.
    """

    queryset = Alert.objects.select_related("service").all().order_by("-received_at")
    serializer_class = AlertSerializer
    permission_classes = [AllowAny]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()

        service_param = self.request.query_params.get("service")
        if service_param:
            qs = qs.filter(service_id=service_param)

        severity_param = self.request.query_params.get("severity")
        if severity_param:
            qs = qs.filter(severity__iexact=severity_param.strip())

        source_param = self.request.query_params.get("source")
        if source_param:
            qs = qs.filter(source__iexact=source_param.strip())

        return qs

    def create(self, request, *args, **kwargs):
        """Ingests, fingerprints, and stores an incoming operational alert."""
        ingest_serializer = AlertIngestSerializer(data=request.data)
        ingest_serializer.is_valid(raise_exception=True)
        validated_data = ingest_serializer.validated_data

        alert = ingest_alert(
            service=validated_data["service"],
            severity=validated_data["severity"],
            message=validated_data["message"],
            source=validated_data["source"],
            metadata=validated_data.get("metadata"),
        )

        response_serializer = AlertSerializer(alert)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
