from datetime import datetime, timedelta
from zoneinfo import available_timezones

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.params import datetime_param, int_param
from apps.core.views import actor

from . import selectors

MAX_WINDOW = timedelta(days=366)

WINDOW_PARAMS = [
    OpenApiParameter("since", str, description="ISO-8601, default 30 days ago"),
    OpenApiParameter("until", str, description="ISO-8601, default now"),
    OpenApiParameter("service", int),
    OpenApiParameter("team", int),
]


def _instant(request: Request, name: str, default: datetime) -> datetime:
    return datetime_param(request.query_params, name) or default


def _window(request: Request) -> selectors.Window:
    now = timezone.now()
    since = _instant(request, "since", now - timedelta(days=30))
    until = _instant(request, "until", now)
    if not (since < until and until - since <= MAX_WINDOW):
        raise ValidationError({"since": "Window must be positive and at most 366 days."})

    params = request.query_params
    return selectors.Window(
        since=since,
        until=until,
        service=int_param(params, "service"),
        team=int_param(params, "team"),
    )


class UrgencySplitSerializer(serializers.Serializer):
    high = serializers.IntegerField()
    low = serializers.IntegerField()


class NoisyServiceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    alerts = serializers.IntegerField()
    incidents = serializers.IntegerField()


class SummarySerializer(serializers.Serializer):
    since = serializers.DateTimeField()
    until = serializers.DateTimeField()
    incidents = serializers.IntegerField()
    by_urgency = UrgencySplitSerializer()
    time_to_first_response_seconds = serializers.FloatField(allow_null=True)
    mtta_seconds = serializers.FloatField(allow_null=True)
    mttr_seconds = serializers.FloatField(allow_null=True)
    escalation_rate = serializers.FloatField(allow_null=True)
    noisy_services = NoisyServiceSerializer(many=True)


class DayPointSerializer(serializers.Serializer):
    date = serializers.DateField()
    incidents = serializers.IntegerField()
    high = serializers.IntegerField()
    low = serializers.IntegerField()
    time_to_first_response_seconds = serializers.FloatField(allow_null=True)
    mtta_seconds = serializers.FloatField(allow_null=True)
    mttr_seconds = serializers.FloatField(allow_null=True)


class SummaryView(APIView):
    @extend_schema(parameters=WINDOW_PARAMS, responses=SummarySerializer)
    def get(self, request: Request) -> Response:
        data = selectors.summary(actor(request), _window(request))
        return Response(SummarySerializer(data).data)


class TimeseriesView(APIView):
    @extend_schema(
        parameters=[
            *WINDOW_PARAMS,
            OpenApiParameter("tz", str, description="IANA zone; default your profile's"),
        ],
        responses=DayPointSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        tz = request.query_params.get("tz") or actor(request).timezone
        if tz not in available_timezones():
            raise ValidationError({"tz": "Unknown IANA timezone."})
        data = selectors.timeseries(actor(request), _window(request), tz)
        return Response(DayPointSerializer(data, many=True).data)
