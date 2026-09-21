from rest_framework import permissions, viewsets

from .models import EscalationLevel, EscalationPolicy
from .serializers import EscalationLevelSerializer, EscalationPolicySerializer


class EscalationPolicyViewSet(viewsets.ModelViewSet):
    """
    CRUD API endpoint for managing Escalation Policies.
    Supports filtering by team and is_active.
    """

    queryset = (
        EscalationPolicy.objects.select_related("team")
        .prefetch_related("levels__target_user")
        .all()
        .order_by("name")
    )
    serializer_class = EscalationPolicySerializer
    permission_classes = [permissions.AllowAny]
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

        return qs


class EscalationLevelViewSet(viewsets.ModelViewSet):
    """
    CRUD API endpoint for managing individual Escalation Levels within policies.
    Supports filtering by policy.
    """

    queryset = (
        EscalationLevel.objects.select_related("policy", "target_user")
        .all()
        .order_by("order")
    )
    serializer_class = EscalationLevelSerializer
    permission_classes = [permissions.AllowAny]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()

        policy_param = self.request.query_params.get("policy")
        if policy_param:
            qs = qs.filter(policy_id=policy_param)

        target_type_param = self.request.query_params.get("target_type")
        if target_type_param:
            qs = qs.filter(target_type=target_type_param.strip().upper())

        return qs
