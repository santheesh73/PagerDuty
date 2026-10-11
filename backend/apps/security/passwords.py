"""Password reset by email: single-use, expiring tokens, and no way to learn who has an account."""

import logging

from celery import shared_task
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.accounts.models import User

logger = logging.getLogger(__name__)


def reset_link(user: User) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?uid={uid}&token={token}"


@shared_task
def send_reset_email(user_id: int) -> None:
    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        return
    send_mail(
        subject="[Pulse] Reset your password",
        message=(
            "Someone (hopefully you) asked to reset the password for this Pulse account.\n\n"
            f"Choose a new password: {reset_link(user)}\n\n"
            f"The link works once and expires in {settings.PASSWORD_RESET_TIMEOUT // 60} minutes. "
            "If you did not ask for this, ignore this email; your password has not changed.\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )


def user_for(uid: str, token: str) -> User | None:
    """The user a reset link belongs to, if the token is valid. Django's token embeds the password
    hash and last login, so it stops working the moment it is used (or the password changes)."""
    try:
        pk = int(urlsafe_base64_decode(uid).decode())
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    user = User.objects.filter(pk=pk, is_active=True).first()
    if user is None or not default_token_generator.check_token(user, token):
        return None
    return user
