from rest_framework.routers import DefaultRouter

from .views import ScheduleRotationViewSet, ScheduleViewSet

router = DefaultRouter()
router.register(r"schedules", ScheduleViewSet, basename="schedule")
router.register(r"schedule-rotations", ScheduleRotationViewSet, basename="schedule-rotation")

urlpatterns = router.urls
