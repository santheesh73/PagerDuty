"""Every /api/v1/ route, gathered in one place so the public surface is easy to audit."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.accounts.views import CsrfView, LoginView, LogoutView, MeView, TeamViewSet, UserViewSet
from apps.alerting.views import EventsView
from apps.analytics.views import SummaryView, TimeseriesView
from apps.catalog.views import ServiceViewSet
from apps.escalations.views import EscalationPolicyViewSet, OnCallsView
from apps.incidents.views import IncidentViewSet
from apps.notifications.views import (
    ContactView,
    NotificationRuleViewSet,
    NotificationViewSet,
    RotateWebhookSecretView,
    SendPhoneCodeView,
    VerifyPhoneView,
)
from apps.schedules.views import OverrideViewSet, ScheduleViewSet

router = DefaultRouter()
router.register("teams", TeamViewSet, basename="team")
router.register("users", UserViewSet, basename="user")
router.register("services", ServiceViewSet, basename="service")
router.register("escalation-policies", EscalationPolicyViewSet, basename="escalation-policy")
router.register("schedules", ScheduleViewSet, basename="schedule")
router.register("incidents", IncidentViewSet, basename="incident")
router.register("notifications", NotificationViewSet, basename="notification")
router.register("me/notification-rules", NotificationRuleViewSet, basename="notification-rule")

overrides = OverrideViewSet.as_view({"get": "list", "post": "create"})
override_detail = OverrideViewSet.as_view(
    {"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}
)

urlpatterns = [
    path("events/", EventsView.as_view(), name="events"),
    path("auth/csrf/", CsrfView.as_view(), name="csrf"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("me/contact/", ContactView.as_view(), name="me-contact"),
    path(
        "me/contact/webhook/rotate-secret/",
        RotateWebhookSecretView.as_view(),
        name="me-contact-rotate-secret",
    ),
    path("me/contact/phone/send-code/", SendPhoneCodeView.as_view(), name="me-phone-send-code"),
    path("me/contact/phone/verify/", VerifyPhoneView.as_view(), name="me-phone-verify"),
    path("oncalls/", OnCallsView.as_view(), name="oncalls"),
    path("analytics/summary/", SummaryView.as_view(), name="analytics-summary"),
    path("analytics/timeseries/", TimeseriesView.as_view(), name="analytics-timeseries"),
    path("schedules/<int:schedule_pk>/overrides/", overrides, name="schedule-overrides"),
    path(
        "schedules/<int:schedule_pk>/overrides/<int:pk>/",
        override_detail,
        name="schedule-override-detail",
    ),
    path("", include(router.urls)),
]
