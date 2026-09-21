from django.db.models import Count, Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Team, TeamMembership, User
from .serializers import TeamMembershipSerializer, TeamSerializer, UserSerializer


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for listing and retrieving users.
    Supports filtering by team via ?team=<team_id>.
    """

    queryset = User.objects.all().order_by("username")
    serializer_class = UserSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = super().get_queryset()
        team_id = self.request.query_params.get("team")
        if team_id:
            qs = qs.filter(team_memberships__team_id=team_id, team_memberships__is_active=True)
        return qs.distinct()


class TeamViewSet(viewsets.ModelViewSet):
    """
    API endpoint for Team lifecycle management.
    Annotates active_member_count to eliminate N+1 query overhead.
    Supports filtering by active status via ?is_active=true.
    """

    serializer_class = TeamSerializer
    permission_classes = [AllowAny]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = Team.objects.annotate(
            active_member_count=Count(
                "memberships",
                filter=Q(memberships__is_active=True),
            )
        ).order_by("name")

        is_active_param = self.request.query_params.get("is_active")
        if is_active_param is not None:
            is_active = is_active_param.lower() in ("true", "1")
            qs = qs.filter(is_active=is_active)

        return qs

    @action(detail=True, methods=["get"], url_path="members")
    def members(self, request, pk=None):
        """
        Retrieves memberships for a specific team.
        Supports filtering by active status via ?is_active=true.
        """
        # Ensure team exists first (raises 404 if nonexistent)
        if not Team.objects.filter(pk=pk).exists():
            raise NotFound(detail=f"Team with ID '{pk}' not found.")

        memberships = (
            TeamMembership.objects.filter(team_id=pk)
            .select_related("user", "team")
            .order_by("user__username")
        )

        is_active_param = request.query_params.get("is_active")
        if is_active_param is not None:
            is_active = is_active_param.lower() in ("true", "1")
            memberships = memberships.filter(is_active=is_active)

        serializer = TeamMembershipSerializer(memberships, many=True)
        return Response(serializer.data)


class TeamMembershipViewSet(
    viewsets.GenericViewSet,
    viewsets.mixins.CreateModelMixin,
    viewsets.mixins.UpdateModelMixin,
    viewsets.mixins.DestroyModelMixin,
):
    """
    API endpoint for TeamMembership management.
    Policy: Soft-deactivates memberships upon DELETE to maintain auditability.
    """

    queryset = TeamMembership.objects.select_related("user", "team").all()
    serializer_class = TeamMembershipSerializer
    permission_classes = [AllowAny]
    http_method_names = ["post", "patch", "delete", "head", "options"]

    def perform_destroy(self, instance: TeamMembership):
        """Soft-deactivate membership by marking is_active=False."""
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)
