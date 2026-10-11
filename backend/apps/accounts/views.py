import hashlib
import logging

from django.conf import settings
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

from apps.core import ratelimit
from apps.core.params import int_param
from apps.core.permissions import member_team_ids
from apps.core.throttling import LoginThrottle
from apps.core.views import actor
from apps.security import audit, mfa
from apps.security.views import start_pending

from .models import Membership, Team, User
from .serializers import (
    LoginSerializer,
    MeSerializer,
    TeamMemberSerializer,
    TeamSerializer,
    UserSummarySerializer,
)

logger = logging.getLogger(__name__)


def _lockout_key(email: str) -> str:
    return "login-fail:" + hashlib.sha256(email.encode()).hexdigest()[:32]


def _locked_out(email: str) -> bool:
    try:
        failures = ratelimit.count(_lockout_key(email))
        return failures >= settings.LOGIN_LOCKOUT_FAILURES
    except Exception:
        return False  # Redis down: the per-address throttle still applies


def _count_failure(email: str) -> None:
    try:
        ratelimit.hit(_lockout_key(email), settings.LOGIN_LOCKOUT_SECONDS)
    except Exception:
        logger.warning("login lockout counter unavailable")


def _clear_failures(email: str) -> None:
    try:
        ratelimit.reset(_lockout_key(email))
    except Exception:
        logger.warning("login lockout counter unavailable")


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    @extend_schema(
        request=LoginSerializer,
        responses=MeSerializer,
        description='Signs in, or answers `{"mfa_required": true}` when the account has '
        "two-factor authentication: then POST the code to /auth/mfa/.",
    )
    def post(self, request: Request) -> Response:
        payload = LoginSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        email = payload.validated_data["email"].lower()
        if _locked_out(email):
            # Checked before the password, so a guesser learns nothing even with the right one.
            audit.record("auth.login_locked", request=request, attempted_email=email)
            return Response(
                {
                    "error": {
                        "code": "too_many_attempts",
                        "message": "Too many failed sign-ins for this account. Try again later.",
                        "details": {},
                    }
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        user = authenticate(request, username=email, password=payload.validated_data["password"])
        if user is None:
            _count_failure(email)
            audit.record("auth.login_failed", request=request, attempted_email=email)
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
        _clear_failures(email)
        if mfa.enabled(user):
            start_pending(request, user)
            return Response({"mfa_required": True})
        login(request, user)
        audit.record("auth.login", request=request, actor=user, mfa=None)
        return Response(MeSerializer(user).data)


class LogoutView(APIView):
    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        audit.record("auth.logout", request=request)
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
        teams = Team.objects.order_by("name", "id")
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
        return Response(
            TeamMemberSerializer(memberships.order_by("user__name", "user_id"), many=True).data
        )


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
        if (team := int_param(self.request.query_params, "team")) is not None:
            users = users.filter(memberships__team_id=team)
        return users.distinct().order_by("name", "id")
