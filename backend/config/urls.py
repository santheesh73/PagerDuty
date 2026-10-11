from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core.health import healthz, readyz
from apps.core.metrics import metrics_view
from apps.notifications import action_views, webhooks

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("readyz", readyz, name="readyz"),
    path("metrics", metrics_view, name="metrics"),
    path("a/<str:token>/", action_views.action_link, name="action-link"),
    path("api/v1/webhooks/twilio/status/", webhooks.twilio_status, name="twilio-status"),
    path("api/v1/webhooks/twilio/voice/<str:token>/", webhooks.twilio_voice, name="twilio-voice"),
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/v1/", include("config.api_urls")),
]
