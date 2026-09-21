from rest_framework.routers import DefaultRouter

from .views import EscalationLevelViewSet, EscalationPolicyViewSet

router = DefaultRouter()
router.register(r"escalation-policies", EscalationPolicyViewSet, basename="escalation-policy")
router.register(r"escalation-levels", EscalationLevelViewSet, basename="escalation-level")

urlpatterns = router.urls
