import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import env_bool

# Refuse to boot with an unsafe configuration rather than silently fall back. NUM_PROXIES is
# the number of proxies in front of the app ("0" for none): unset, DRF trusts the whole
# X-Forwarded-For header, so a client picks the address its sign-in limits and audit log see.
for required in ("SECRET_KEY", "ALLOWED_HOSTS", "DATABASE_URL", "NUM_PROXIES"):
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
# On by default: browsers then refuse plain HTTP for this host for a year. Plain-HTTP local
# stacks (docker-compose.prod.yml on localhost) are unaffected: browsers ignore HSTS sent over
# HTTP. Subdomains and preload stay opt-in because they are hard to undo (DECISIONS #18).
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", str(365 * 24 * 3600)))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
API_DOCS = env_bool("API_DOCS", False)
REQUIRE_MFA_FOR_ADMINS = env_bool("REQUIRE_MFA_FOR_ADMINS", True)
# "__Host-" cookies are only accepted over HTTPS, for this exact host and path "/": a sibling
# subdomain cannot set or overwrite them. Only meaningful with secure cookies.
if SESSION_COOKIE_SECURE:
    SESSION_COOKIE_NAME = "__Host-sessionid"
SECURE_CONTENT_TYPE_NOSNIFF = True
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# `check --deploy` warns until HSTS covers subdomains and asks for preload. Both are opt-in on
# purpose: they apply to every subdomain of the domain, and preload is effectively irreversible.
# Silenced only while not enabled, so turning them on brings the checks back.
SILENCED_SYSTEM_CHECKS = [
    *([] if SECURE_HSTS_INCLUDE_SUBDOMAINS else ["security.W005"]),
    *([] if SECURE_HSTS_PRELOAD else ["security.W021"]),
]
