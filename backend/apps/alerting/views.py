import hmac

from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Service
from apps.core import limits, metrics
from apps.core.errors import DomainError
from apps.core.throttling import RoutingKeyThrottle

from .actions import Event, ingest
from .serializers import EventResultSerializer, EventSerializer


class InvalidRoutingKey(DomainError):
    code = "invalid_routing_key"
    http_status = status.HTTP_403_FORBIDDEN


class EventsView(APIView):
    """Events API v1. Authenticated solely by `routing_key` (a service's integration key).

    No session, no CSRF: monitoring systems post here directly.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [RoutingKeyThrottle]

    @extend_schema(
        request=EventSerializer,
        responses={202: EventResultSerializer},
        examples=[
            OpenApiExample(
                "Trigger",
                value={
                    "routing_key": "<integration key>",
                    "event_action": "trigger",
                    "dedup_key": "db-1/disk",
                    "payload": {
                        "summary": "Disk 95% full on db-1",
                        "severity": "critical",
                        "source": "prometheus",
                    },
                },
                request_only=True,
            )
        ],
    )
    def post(self, request: Request) -> Response:
        # Check the raw size before parsing anything else into memory.
        limits.enforce("event_payload_bytes", len(request.body))
        payload = EventSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        service = self._service_for(data["routing_key"])
        body = data.get("payload") or {}
        result = ingest(
            service,
            Event(
                action=data["event_action"],
                dedup_key=data.get("dedup_key") or None,
                summary=body.get("summary", ""),
                severity=body.get("severity", "critical"),
                source=body.get("source", ""),
                custom_details=body.get("custom_details") or {},
            ),
        )
        metrics.INGEST_REQUESTS.labels(result.status).inc()
        return Response(
            EventResultSerializer(
                {
                    "status": result.status,
                    "dedup_key": result.dedup_key,
                    "incident_id": result.incident_id,
                }
            ).data,
            status=status.HTTP_202_ACCEPTED,
        )

    @staticmethod
    def _service_for(routing_key: str) -> Service:
        service = (
            Service.objects.select_related("escalation_policy")
            .filter(integration_key=routing_key)
            .first()
        )
        # Constant-time compare on the hit path; the lookup itself is by unique index.
        if service is None or not hmac.compare_digest(service.integration_key, routing_key):
            raise InvalidRoutingKey("Unknown routing key.")
        return service
