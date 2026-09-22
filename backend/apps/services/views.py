from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from .models import Service
from .serializers import ServiceSerializer


class ServiceViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing monitored Services.
    Supports filtering by team, status, and active state.
    """

    queryset = Service.objects.select_related("team", "escalation_policy").all().order_by("name")
    serializer_class = ServiceSerializer
    permission_classes = [AllowAny]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()

        team_param = self.request.query_params.get("team")
        if team_param:
            cleaned_team = str(team_param).strip()
            if cleaned_team.isdigit():
                qs = qs.filter(team_id=int(cleaned_team))
            else:
                qs = qs.none()

        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status__iexact=status_param.strip())

        is_active_param = self.request.query_params.get("is_active")
        if is_active_param is not None:
            is_active = is_active_param.lower() in ("true", "1")
            qs = qs.filter(is_active=is_active)

        return qs
