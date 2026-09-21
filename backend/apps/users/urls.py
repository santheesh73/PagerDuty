from rest_framework.routers import DefaultRouter

from .views import TeamMembershipViewSet, TeamViewSet, UserViewSet

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")
router.register(r"teams", TeamViewSet, basename="team")
router.register(r"team-memberships", TeamMembershipViewSet, basename="team-membership")

urlpatterns = router.urls
