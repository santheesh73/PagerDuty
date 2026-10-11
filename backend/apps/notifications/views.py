import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.core import limits
from apps.core.throttling import FailOpenMixin
from apps.core.views import actor
from apps.security import audit

from . import actions, providers
from .channels import unavailable_reason
from .models import Notification, NotificationRule, UserContact
from .serializers import (
    CodeSerializer,
    ContactSerializer,
    ContactUpdateResponseSerializer,
    ContactUpdateSerializer,
    CountSerializer,
    NotificationRuleSerializer,
    NotificationSerializer,
    SecretResponseSerializer,
)


class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Your in-app inbox. Only in-app rows: email copies are delivery records, not inbox items."""

    serializer_class = NotificationSerializer

    def get_queryset(self) -> QuerySet[Notification]:
        if getattr(self, "swagger_fake_view", False):  # OpenAPI generation
            return Notification.objects.none()
        rows = Notification.objects.filter(
            user=actor(self.request), channel=Notification.Channel.IN_APP
        ).select_related("incident")
        if self.request.query_params.get("unread") in {"1", "true"}:
            rows = rows.filter(read_at__isnull=True)
        return rows.order_by("-created_at", "-id")

    @extend_schema(parameters=[OpenApiParameter("unread", bool)])
    def list(self, request: Request, *args: object, **kwargs: object) -> Response:
        return super().list(request, *args, **kwargs)

    @extend_schema(request=None, responses=NotificationSerializer)
    @action(detail=True, methods=["post"])
    def read(self, request: Request, pk: str | None = None) -> Response:
        return Response(NotificationSerializer(actions.mark_read(self.get_object())).data)

    @extend_schema(request=None, responses=CountSerializer)
    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request: Request) -> Response:
        return Response({"count": actions.mark_all_read(actor(request))})

    @extend_schema(responses=CountSerializer)
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request: Request) -> Response:
        count = self.get_queryset().filter(read_at__isnull=True).count()
        return Response({"count": count})


# --- contact details and personal notification rules -----------------------------------------

CODE_TTL = timedelta(minutes=10)
CODE_MAX_ATTEMPTS = 5


class PhoneCodeThrottle(FailOpenMixin, UserRateThrottle):
    """A verification code is an SMS that costs money and can be aimed at any number a user
    types, so sending is rate limited per user."""

    scope = "phone_code"


def _contact_for_update(user: User) -> UserContact:
    contact, _ = UserContact.objects.select_for_update().get_or_create(user=user)
    return contact


def _code_hash(user_id: int, phone: str, code: str) -> str:
    key = hmac.new(settings.SECRET_KEY.encode(), b"pulse.phone-code.v1", hashlib.sha256).digest()
    return hmac.new(key, f"{user_id}:{phone}:{code}".encode(), hashlib.sha256).hexdigest()


class ContactView(APIView):
    """The signed-in user's phone number and webhook. Always their own: there is no user id."""

    @extend_schema(responses=ContactSerializer)
    def get(self, request: Request) -> Response:
        contact = UserContact.objects.filter(user=actor(request)).first()
        return Response(ContactSerializer.of(contact))

    @extend_schema(request=ContactUpdateSerializer, responses=ContactUpdateResponseSerializer)
    def patch(self, request: Request) -> Response:
        payload = ContactUpdateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        secret = None
        with transaction.atomic():
            contact = _contact_for_update(actor(request))
            if "phone_number" in data and data["phone_number"] != contact.phone_number:
                contact.phone_number = data["phone_number"]
                contact.phone_verified_at = None  # a new number is unverified until proven
                contact.phone_code_hash = ""
                contact.phone_code_expires_at = None
                contact.phone_code_attempts = 0
            if "webhook_url" in data and data["webhook_url"] != contact.webhook_url:
                contact.webhook_url = data["webhook_url"]
                secret = secrets.token_urlsafe(32) if contact.webhook_url else ""
                contact.webhook_secret = secret
            contact.save()
            if not contact.phone_verified:  # rules that need a verified phone can no longer work
                NotificationRule.objects.filter(
                    user=actor(request),
                    channel__in=[Notification.Channel.SMS, Notification.Channel.VOICE],
                ).update(enabled=False)
            if not contact.webhook_url:
                NotificationRule.objects.filter(
                    user=actor(request), channel=Notification.Channel.WEBHOOK
                ).update(enabled=False)
        audit.record("contact.updated", request=request, fields=sorted(data))
        body = ContactSerializer.of(contact)
        if secret:
            body["webhook_secret"] = secret
        return Response(body)


class RotateWebhookSecretView(APIView):
    @extend_schema(request=None, responses=SecretResponseSerializer)
    def post(self, request: Request) -> Response:
        with transaction.atomic():
            contact = _contact_for_update(actor(request))
            if not contact.webhook_url:
                raise serializers.ValidationError({"webhook_url": "Set a webhook URL first."})
            contact.webhook_secret = secrets.token_urlsafe(32)
            contact.save(update_fields=["webhook_secret", "updated_at"])
        audit.record("contact.webhook_secret_rotated", request=request)
        return Response({"webhook_secret": contact.webhook_secret})


class SendPhoneCodeView(APIView):
    throttle_classes = [PhoneCodeThrottle]

    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        if not providers.configured():
            raise serializers.ValidationError("SMS is not enabled on this server.")
        with transaction.atomic():
            contact = _contact_for_update(actor(request))
            if not contact.phone_number:
                raise serializers.ValidationError({"phone_number": "Add a phone number first."})
            code = f"{secrets.randbelow(10**6):06d}"
            contact.phone_code_hash = _code_hash(contact.user_id, contact.phone_number, code)
            contact.phone_code_expires_at = timezone.now() + CODE_TTL
            contact.phone_code_attempts = 0
            contact.save()
            number = contact.phone_number
        try:
            providers.send_sms(
                number, f"Pulse verification code: {code}. It expires in 10 minutes."
            )
        except Exception as exc:
            raise serializers.ValidationError("Could not send the code. Check the number.") from exc
        return Response(status=status.HTTP_204_NO_CONTENT)


class VerifyPhoneView(APIView):
    @extend_schema(request=CodeSerializer, responses=ContactSerializer)
    def post(self, request: Request) -> Response:
        payload = CodeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        with transaction.atomic():
            contact = _contact_for_update(actor(request))
            now = timezone.now()
            if not contact.phone_code_hash or (
                contact.phone_code_expires_at and contact.phone_code_expires_at <= now
            ):
                raise serializers.ValidationError(
                    {"code": "That code has expired. Request a new one."}
                )
            if contact.phone_code_attempts >= CODE_MAX_ATTEMPTS:
                raise serializers.ValidationError(
                    {"code": "Too many attempts. Request a new code."}
                )
            contact.phone_code_attempts += 1
            expected = _code_hash(
                contact.user_id, contact.phone_number, payload.validated_data["code"]
            )
            if not hmac.compare_digest(expected, contact.phone_code_hash):
                contact.save(update_fields=["phone_code_attempts", "updated_at"])
                # Commit the spent attempt: raising here would roll it back and allow unlimited
                # guesses.
                result: tuple[str, UserContact | None] = ("invalid", None)
            else:
                contact.phone_verified_at = now
                contact.phone_code_hash = ""
                contact.phone_code_expires_at = None
                contact.phone_code_attempts = 0
                contact.save()
                result = ("ok", contact)
        if result[0] == "ok":
            audit.record("contact.phone_verified", request=request)
        if result[0] == "invalid":
            raise serializers.ValidationError({"code": "That code is not right."})
        return Response(ContactSerializer.of(result[1]))


class NotificationRuleViewSet(viewsets.ModelViewSet):
    """Your own paging plan: "after N minutes, if still unanswered, use X". No team scoping
    because there is nothing shared: every row belongs to the caller or does not exist."""

    serializer_class = NotificationRuleSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[NotificationRule]:
        if getattr(self, "swagger_fake_view", False):
            return NotificationRule.objects.none()
        return NotificationRule.objects.filter(user=actor(self.request))

    def _check_channel(self, channel: str, enabled: bool) -> None:
        if not enabled:
            return
        contact = UserContact.objects.filter(user=actor(self.request)).first()
        reason = unavailable_reason(channel, contact)
        if reason:
            raise serializers.ValidationError({"channel": reason})

    def perform_create(self, serializer: NotificationRuleSerializer) -> None:  # type: ignore[override]
        with transaction.atomic():
            mine = NotificationRule.objects.select_for_update().filter(user=actor(self.request))
            existing = list(mine.values_list("position", flat=True))
            limits.enforce("notification_rules", len(existing) + 1)
            self._check_channel(
                serializer.validated_data["channel"], serializer.validated_data.get("enabled", True)
            )
            serializer.save(user=actor(self.request), position=max(existing, default=-1) + 1)

    def perform_update(self, serializer: NotificationRuleSerializer) -> None:  # type: ignore[override]
        rule: NotificationRule = serializer.instance  # type: ignore[assignment]
        channel = serializer.validated_data.get("channel", rule.channel)
        enabled = serializer.validated_data.get("enabled", rule.enabled)
        self._check_channel(channel, enabled)
        serializer.save()
