"""URL configuration for Incident Management Platform."""
import redis
from django.conf import settings
from django.contrib import admin
from django.db import connection
from django.urls import include, path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """
    Infrastructure health endpoint.
    Validates that Django is alive and inspects core infrastructure connections.
    """
    dependencies = {}

    # Database connectivity check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()
        dependencies["database"] = "ok"
    except Exception as exc:
        dependencies["database"] = f"unavailable: {exc}"

    # Redis connectivity check
    try:
        redis_client = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=1)
        redis_client.ping()
        dependencies["redis"] = "ok"
    except Exception as exc:
        dependencies["redis"] = f"unavailable: {exc}"

    return Response(
        {
            "status": "ok",
            "dependencies": dependencies,
        },
        status=200,
    )


# Root API URL patterns
api_patterns = [
    path("health/", health_check, name="health_check"),
    path("", include("apps.users.urls")),
    path("", include("apps.services.urls")),
    path("", include("apps.alerts.urls")),
    path("", include("apps.incidents.urls")),
    path("", include("apps.scheduling.urls")),
    path("", include("apps.escalation.urls")),
    path("", include("apps.notifications.urls")),
    path("", include("apps.analytics.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include((api_patterns, "api"))),
]
