from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .services import (
    calculate_analytics_summary,
    calculate_incident_trend,
    calculate_incidents_by_service,
    calculate_severity_distribution,
    parse_range_param,
)


@api_view(["GET"])
@permission_classes([AllowAny])
def analytics_summary_view(request):
    """
    GET /api/analytics/summary/?range=30d
    Returns system incident counts, MTTA, and MTTR.
    """
    days = parse_range_param(request.query_params.get("range"))
    data = calculate_analytics_summary(days=days)
    return Response(data)


@api_view(["GET"])
@permission_classes([AllowAny])
def incidents_by_service_view(request):
    """
    GET /api/analytics/incidents-by-service/?range=30d
    Returns incident counts aggregated by service.
    """
    days = parse_range_param(request.query_params.get("range"))
    data = calculate_incidents_by_service(days=days)
    return Response(data)


@api_view(["GET"])
@permission_classes([AllowAny])
def severity_distribution_view(request):
    """
    GET /api/analytics/severity-distribution/?range=30d
    Returns incident counts aggregated by severity.
    """
    days = parse_range_param(request.query_params.get("range"))
    data = calculate_severity_distribution(days=days)
    return Response(data)


@api_view(["GET"])
@permission_classes([AllowAny])
def incident_trend_view(request):
    """
    GET /api/analytics/trend/?range=30d
    Returns daily incident creation counts across the window.
    """
    days = parse_range_param(request.query_params.get("range"))
    data = calculate_incident_trend(days=days)
    return Response(data)
