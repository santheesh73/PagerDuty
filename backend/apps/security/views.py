import hashlib
import logging

from django.conf import settings
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_POST
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.serializers import MeSerializer
from apps.core import dispatch, ratelimit
from apps.core.params import int_param
from apps.core.permissions import admin_team_ids
from apps.core.throttling import AddressThrottle, FailOpenMixin
from apps.core.views import actor, no_store

from . import audit, mfa, passwords, sessions, totp
from .models import AuditEvent, SessionRecord
from .serializers import (
    AuditEventSerializer,
    BackupCodesSerializer,
    DisableMfaSerializer,
    MfaCodeSerializer,
    MfaSetupSerializer,
    MfaStatusSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RevokedCountSerializer,
    SessionSerializer,
)

logger = logging.getLogger(__name__)

PENDING = "mfa_pending"
PENDING_TTL = 300  # seconds between the password step and the code step
PENDING_ATTEMPTS = 5


def _error(code: str, message: str, http: int) -> Response:
    return Response({"error": {"code": code, "message": message, "details": {}}}, status=http)


class MfaThrottle(AddressThrottle):
    scope = "mfa"


class PasswordResetThrottle(AddressThrottle):
    scope = "password_reset"


class SensitiveUserThrottle(FailOpenMixin, UserRateThrottle):
    scope = "mfa"


# --- the second sign-in step -------------------------------------------------------------------


def _code_failures_key(user: User) -> str:
    return f"mfa-fail:{user.pk}"


def _codes_locked(user: User) -> bool:
    """Wrong codes are counted per account across password steps, not only per step: the
    per-step cap alone let anyone who knew the password keep starting new steps."""
    try:
        return ratelimit.count(_code_failures_key(user)) >= settings.MFA_LOCKOUT_FAILURES
    except Exception:
        return False  # cache down: the per-address and per-step limits still apply


def _count_code_failure(user: User) -> None:
    try:
        ratelimit.hit(_code_failures_key(user), settings.MFA_LOCKOUT_SECONDS)
    except Exception:
        logger.warning("MFA lockout counter unavailable")


def _clear_code_failures(user: User) -> None:
    try:
        ratelimit.reset(_code_failures_key(user))
    except Exception:
        logger.warning("MFA lockout counter unavailable")


def start_pending(request: HttpRequest, user: User) -> None:
    """Password was right and the account has MFA: remember who, briefly, without logging in."""
    request.session.cycle_key()  # no fixation across the two steps
    request.session[PENDING] = {"uid": user.pk, "at": timezone.now().timestamp(), "tries": 0}


@method_decorator(csrf_protect, name="dispatch")
class LoginMfaView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [MfaThrottle]

    @extend_schema(request=MfaCodeSerializer, responses=MeSerializer)
    def post(self, request: Request) -> Response:
        payload = MfaCodeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        pending = request.session.get(PENDING)
        if not pending or timezone.now().timestamp() - pending["at"] > PENDING_TTL:
            request.session.pop(PENDING, None)
            return _error("mfa_session_expired", "Sign in again.", status.HTTP_401_UNAUTHORIZED)
        user = User.objects.filter(pk=pending["uid"], is_active=True).first()
        if user is None:
            request.session.pop(PENDING, None)
            return _error("mfa_session_expired", "Sign in again.", status.HTTP_401_UNAUTHORIZED)
        if _codes_locked(user):
            # Checked before the code, so a guesser learns nothing even with the right one.
            audit.record("auth.mfa_locked", request=request, actor=user)
            return _error(
                "too_many_attempts",
                "Too many wrong codes for this account. Try again later.",
                status.HTTP_429_TOO_MANY_REQUESTS,
            )
        method = mfa.verify(user, payload.validated_data["code"])
        if method is None:
            _count_code_failure(user)
            pending["tries"] += 1
            if pending["tries"] >= PENDING_ATTEMPTS:
                request.session.pop(PENDING, None)  # back to the password step
            else:
                request.session[PENDING] = pending
            audit.record("auth.mfa_failed", request=request, actor=user)
            return _error("invalid_code", "That code is not right.", status.HTTP_401_UNAUTHORIZED)
        _clear_code_failures(user)
        request.session.pop(PENDING, None)
        login(request._request, user, backend="django.contrib.auth.backends.ModelBackend")
        audit.record("auth.login", request=request, actor=user, mfa=method)
        if method == "backup":
            audit.record(
                "auth.backup_code_used",
                request=request,
                actor=user,
                remaining=mfa.remaining_backup_codes(user),
            )
        return Response(MeSerializer(user).data)


# --- MFA enrolment -----------------------------------------------------------------------------


class MfaView(APIView):
    @extend_schema(responses=MfaStatusSerializer)
    def get(self, request: Request) -> Response:
        user = actor(request)
        return Response(
            {
                "enabled": mfa.enabled(user),
                "enforced": mfa.required(user),
                "backup_codes_remaining": mfa.remaining_backup_codes(user),
            }
        )


class MfaSetupView(APIView):
    @extend_schema(request=None, responses=MfaSetupSerializer)
    def post(self, request: Request) -> Response:
        user = actor(request)
        if mfa.enabled(user):
            return _error("mfa_already_enabled", "Turn MFA off before setting it up again.", 409)
        device = mfa.begin_setup(user)
        return no_store(
            Response(
                {
                    "secret": device.secret,
                    "otpauth_uri": totp.provisioning_uri(device.secret, user.email),
                }
            )
        )


class MfaConfirmView(APIView):
    throttle_classes = [SensitiveUserThrottle]

    @extend_schema(request=MfaCodeSerializer, responses=BackupCodesSerializer)
    def post(self, request: Request) -> Response:
        payload = MfaCodeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        codes = mfa.confirm(actor(request), payload.validated_data["code"])
        if codes is None:
            raise serializers.ValidationError(
                {"code": "That code is not right. Check the time on your phone."}
            )
        audit.record("mfa.enabled", request=request)
        return no_store(Response({"backup_codes": codes}))


class MfaBackupCodesView(APIView):
    throttle_classes = [SensitiveUserThrottle]

    @extend_schema(request=MfaCodeSerializer, responses=BackupCodesSerializer)
    def post(self, request: Request) -> Response:
        payload = MfaCodeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        user = actor(request)
        if mfa.verify(user, payload.validated_data["code"]) != "totp":
            raise serializers.ValidationError({"code": "Enter a code from your authenticator app."})
        audit.record("mfa.backup_codes_regenerated", request=request)
        return no_store(Response({"backup_codes": mfa.regenerate_backup_codes(user)}))


class MfaDisableView(APIView):
    throttle_classes = [SensitiveUserThrottle]

    @extend_schema(request=DisableMfaSerializer, responses={204: None})
    def post(self, request: Request) -> Response:
        payload = DisableMfaSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        user = actor(request)
        if mfa.required(user):
            return _error(
                "mfa_required", "Team admins must keep two-factor authentication on.", 403
            )
        if not user.check_password(payload.validated_data["password"]) or not mfa.verify(
            user, payload.validated_data["code"]
        ):
            raise serializers.ValidationError("Password or code is not right.")
        mfa.disable(user)
        audit.record("mfa.disabled", request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- passwords ---------------------------------------------------------------------------------


class PasswordChangeView(APIView):
    throttle_classes = [SensitiveUserThrottle]

    @extend_schema(request=PasswordChangeSerializer, responses={204: None})
    def post(self, request: Request) -> Response:
        user = actor(request)
        payload = PasswordChangeSerializer(data=request.data, context={"user": user})
        payload.is_valid(raise_exception=True)
        user.set_password(payload.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        update_session_auth_hash(request._request, user)  # keep this session, end the others
        ended = sessions.revoke(user, keep=request.session.session_key)
        audit.record("auth.password_changed", request=request, other_sessions_ended=ended)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _email_bucket(email: str) -> str:
    return "pwreset:" + hashlib.sha256(email.lower().encode()).hexdigest()[:32]


@method_decorator(csrf_protect, name="dispatch")
class PasswordResetRequestView(APIView):
    """Always 204, whether or not the address has an account (no enumeration). The email is sent
    by a task, so the response time does not depend on SMTP either."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [PasswordResetThrottle]

    @extend_schema(request=PasswordResetRequestSerializer, responses={204: None})
    def post(self, request: Request) -> Response:
        payload = PasswordResetRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        email = payload.validated_data["email"].lower()
        bucket = _email_bucket(email)
        try:
            per_address = ratelimit.hit(bucket, 3600)
        except Exception:
            per_address = 0
        user = User.objects.filter(email=email, is_active=True).first()
        if user is not None and per_address <= 3:  # at most 3 emails an hour to one address
            dispatch.on_commit(passwords.send_reset_email, user.pk)
            audit.record("auth.password_reset_requested", request=request, actor=user)
        elif user is None:
            # The same database write for an address with no account, so how long the request
            # takes does not say whether one exists.
            audit.record("auth.password_reset_requested", request=request, attempted_email=email)
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(csrf_protect, name="dispatch")
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [PasswordResetThrottle]

    @extend_schema(request=PasswordResetConfirmSerializer, responses={204: None})
    def post(self, request: Request) -> Response:
        payload = PasswordResetConfirmSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        user = passwords.user_for(data["uid"], data["token"])
        if user is None:
            return _error("invalid_token", "This reset link is invalid or has expired.", 400)
        try:
            validate_password(data["new_password"], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)}) from exc
        with transaction.atomic():
            user.set_password(data["new_password"])
            user.save(update_fields=["password", "updated_at"])
            ended = sessions.revoke(user)  # whoever had the old password is out
        audit.record("auth.password_reset", request=request, actor=user, sessions_ended=ended)
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- sessions ----------------------------------------------------------------------------------


class SessionViewSet(mixins.ListModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Your signed-in sessions. Deleting one signs that browser out."""

    serializer_class = SessionSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[SessionRecord]:
        if getattr(self, "swagger_fake_view", False):
            return SessionRecord.objects.none()
        return SessionRecord.objects.filter(user=actor(self.request)).order_by("-created_at", "-id")

    def perform_destroy(self, instance: SessionRecord) -> None:
        from django.contrib.sessions.models import Session

        Session.objects.filter(session_key=instance.session_key).delete()
        instance.delete()
        audit.record("auth.session_revoked", request=self.request)


class RevokeOtherSessionsView(APIView):
    @extend_schema(request=None, responses=RevokedCountSerializer)
    def post(self, request: Request) -> Response:
        ended = sessions.revoke(actor(request), keep=request.session.session_key)
        audit.record("auth.sessions_revoked", request=request, count=ended)
        return Response({"count": ended})


# --- audit log ---------------------------------------------------------------------------------


@extend_schema(
    parameters=[
        OpenApiParameter("action", str, description="Exact action, e.g. auth.login"),
        OpenApiParameter("team", int),
    ]
)
class AuditEventViewSet(viewsets.ReadOnlyModelViewSet):
    """Security-relevant actions in the teams you administer (staff: everything)."""

    serializer_class = AuditEventSerializer

    def get_queryset(self) -> QuerySet[AuditEvent]:
        if getattr(self, "swagger_fake_view", False):
            return AuditEvent.objects.none()
        user = actor(self.request)
        events = AuditEvent.objects.all()
        if not user.is_staff:
            events = events.filter(team_id__in=admin_team_ids(user))
        params = self.request.query_params
        if params.get("action"):
            events = events.filter(action=params["action"])
        if (team := int_param(params, "team")) is not None:
            events = events.filter(team_id=team)
        return events.order_by("-created_at", "-id")


# --- CSP violation reports ---------------------------------------------------------------------


@csrf_exempt
@require_POST
def csp_report(request: HttpRequest) -> HttpResponse:
    """Browsers POST CSP violations here. Logged (truncated, rate limited), never stored."""
    import logging

    if ratelimit.allow("csp-report", request, limit=60):
        logging.getLogger("pulse.csp").warning(
            "csp violation", extra={"report": request.body[:2000].decode(errors="replace")}
        )
    return HttpResponse(status=204)
