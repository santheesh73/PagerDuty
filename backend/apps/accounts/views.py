from django.contrib.auth import authenticate, login, logout
from django.db.models import QuerySet
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import member_team_ids
from apps.core.throttling import LoginThrottle
from apps.core.views import actor

from .models import Membership, Team, User
from .serializers import (
    LoginSerializer,
    MeSerializer,
    TeamMemberSerializer,
    TeamSerializer,
    UserSummarySerializer,
)


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    @extend_schema(request=LoginSerializer, responses=MeSerializer)
    def post(self, request: Request) -> Response:
        payload = LoginSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=payload.validated_data["email"].lower(),
            password=payload.validated_data["password"],
        )
        if user is None:
            return Response(
                {
                    "error": {
                        "code": "invalid_credentials",
                        "message": "Email or password is incorrect.",
                        "details": {},
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        login(request, user)
        return Response(MeSerializer(user).data)


class LogoutView(APIView):
    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class MeView(generics.RetrieveUpdateAPIView):
    """Current user. Also the SPA's bootstrap call: it always sets the CSRF cookie."""

    serializer_class = MeSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch"]

    def get_object(self) -> User:
        return User.objects.prefetch_related("memberships__team").get(pk=actor(self.request).pk)


@extend_schema(responses={204: None})
@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    """Sets the CSRF cookie for anonymous visitors (the login page)."""

    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        return Response(status=status.HTTP_204_NO_CONTENT)


class TeamViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TeamSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[Team]:
        teams = Team.objects.all()
        if not self.request.user.is_authenticated:
            return teams.none()
        if self.request.user.is_staff:
            return teams
        return teams.filter(pk__in=member_team_ids(self.request.user))

    @extend_schema(responses=TeamMemberSerializer(many=True))
    @action(detail=True, methods=["get"])
    def members(self, request: Request, pk: str | None = None) -> Response:
        team = self.get_object()
        memberships = Membership.objects.filter(team=team).select_related("user")
        return Response(TeamMemberSerializer(memberships.order_by("user__name"), many=True).data)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """People the requester can page or schedule: members of any of their teams."""

    serializer_class = UserSummarySerializer
    pagination_class = None

    @extend_schema(parameters=[OpenApiParameter("team", int, description="Limit to one team")])
    def list(self, request: Request, *args: object, **kwargs: object) -> Response:
        return super().list(request, *args, **kwargs)

    def get_queryset(self) -> QuerySet[User]:
        if not self.request.user.is_authenticated:
            return User.objects.none()
        teams = member_team_ids(self.request.user)
        if self.request.user.is_staff:
            users = User.objects.filter(is_active=True)
        else:
            users = User.objects.filter(is_active=True, memberships__team_id__in=teams)
        if team := self.request.query_params.get("team"):
            users = users.filter(memberships__team_id=team)
        return users.distinct().order_by("name")
