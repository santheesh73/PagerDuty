from django.conf import settings
from django.contrib import admin
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import include, path
from django.utils.csp import CSP
from django.views.decorators.csp import csp_override
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core.health import healthz, readyz
from apps.core.metrics import metrics_view
from apps.notifications import action_views, webhooks


def admin_login(request: HttpRequest) -> HttpResponseRedirect:
    """The admin signs in through the app, so it gets the same lockout, MFA and audit trail.
    Django's own admin login form checks only a password."""
    return HttpResponseRedirect(f"{settings.FRONTEND_URL.rstrip('/')}/login?next=/admin/")


admin.site.login = admin_login  # type: ignore[method-assign,assignment]

# Swagger UI loads its assets from jsDelivr and boots with an inline script, so this one page gets
# a looser policy. It renders only the public schema and handles no credentials of its own.
_DOCS_CDN = "https://cdn.jsdelivr.net"
api_docs = csp_override(
    {
        "default-src": [CSP.SELF],
        "script-src": [CSP.SELF, _DOCS_CDN, CSP.UNSAFE_INLINE],
        "style-src": [CSP.SELF, _DOCS_CDN, CSP.UNSAFE_INLINE],
        "img-src": [CSP.SELF, "data:", _DOCS_CDN],
        "connect-src": [CSP.SELF],
        "object-src": [CSP.NONE],
        "frame-ancestors": [CSP.NONE],
    }
)(SpectacularSwaggerView.as_view(url_name="schema"))

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("readyz", readyz, name="readyz"),
    path("metrics", metrics_view, name="metrics"),
    path("a/<str:token>/", action_views.action_link, name="action-link"),
    path("api/v1/webhooks/twilio/status/", webhooks.twilio_status, name="twilio-status"),
    path("api/v1/webhooks/twilio/voice/<str:token>/", webhooks.twilio_voice, name="twilio-voice"),
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", api_docs, name="docs"),
    path("api/v1/", include("config.api_urls")),
]
