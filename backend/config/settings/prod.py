import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import env_bool

# Refuse to boot with an unsafe configuration rather than silently fall back.
for required in ("SECRET_KEY", "ALLOWED_HOSTS", "DATABASE_URL"):
    if not os.environ.get(required):
        raise ImproperlyConfigured(f"{required} must be set in production")

DEBUG = False
SECRET_KEY = os.environ["SECRET_KEY"]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# The SPA's nginx proxies /api here and forwards the browser-facing host, so absolute URLs
# (pagination links, admin redirects) point at the public origin.
USE_X_FORWARDED_HOST = env_bool("USE_X_FORWARDED_HOST", True)
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
# Platform health checks speak plain HTTP inside the network; a 301 would mark us unhealthy.
SECURE_REDIRECT_EXEMPT = [r"^healthz$", r"^readyz$"]
SESSION_COOKIE_SECURE = env_bool("SECURE_COOKIES", True)
CSRF_COOKIE_SECURE = env_bool("SECURE_COOKIES", True)
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "0"))
SECURE_CONTENT_TYPE_NOSNIFF = True
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
