from django.urls import path

from .views import (
    analytics_summary_view,
    incident_trend_view,
    incidents_by_service_view,
    severity_distribution_view,
)

urlpatterns = [
    path("analytics/summary/", analytics_summary_view, name="analytics-summary"),
    path("analytics/incidents-by-service/", incidents_by_service_view, name="analytics-incidents-by-service"),
    path("analytics/severity-distribution/", severity_distribution_view, name="analytics-severity-distribution"),
    path("analytics/trend/", incident_trend_view, name="analytics-trend"),
]
