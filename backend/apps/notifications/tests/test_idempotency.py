import pytest
from django.contrib.auth import get_user_model

from apps.escalation.models import EscalationLevel, EscalationPolicy
from apps.incidents.models import Incident
from apps.notifications.models import Notification
from apps.notifications.services import create_notification
from apps.services.models import Service
from apps.users.models import Team

User = get_user_model()


@pytest.fixture
def idem_setup():
    team = Team.objects.create(name="Idem Team", slug="idem-team")
    user_a = User.objects.create_user(username="user_a", email="a@example.com")
    user_b = User.objects.create_user(username="user_b", email="b@example.com")

    from apps.users.models import TeamMembership
    TeamMembership.objects.create(user=user_a, team=team, role=TeamMembership.Role.ENGINEER)
    TeamMembership.objects.create(user=user_b, team=team, role=TeamMembership.Role.LEAD)

    service = Service.objects.create(name="Idem Service", slug="idem-svc", team=team)
    incident = Incident.objects.create(service=service, title="Incident Idem", fingerprint="fp-idem-notif")

    policy = EscalationPolicy.objects.create(name="Policy Idem", slug="policy-idem", team=team)
    level_1 = EscalationLevel.objects.create(policy=policy, order=1, target_type=EscalationLevel.TargetType.CURRENT_ON_CALL, wait_minutes=5)
    level_2 = EscalationLevel.objects.create(policy=policy, order=2, target_type=EscalationLevel.TargetType.USER, target_user=user_a, wait_minutes=10)

    return {
        "incident": incident,
        "user_a": user_a,
        "user_b": user_b,
        "level_1": level_1,
        "level_2": level_2,
    }


@pytest.mark.django_db
def test_create_notification_dedupes_same_logical_request(idem_setup):
    notif1 = create_notification(
        incident=idem_setup["incident"],
        recipient=idem_setup["user_a"],
        escalation_level=idem_setup["level_1"],
        channel="EMAIL",
    )
    notif2 = create_notification(
        incident=idem_setup["incident"],
        recipient=idem_setup["user_a"],
        escalation_level=idem_setup["level_1"],
        channel="EMAIL",
    )
    assert notif1.id == notif2.id
    assert Notification.objects.count() == 1


@pytest.mark.django_db
def test_create_notification_differentiates_by_level_or_user(idem_setup):
    notif_level_1 = create_notification(
        incident=idem_setup["incident"],
        recipient=idem_setup["user_a"],
        escalation_level=idem_setup["level_1"],
        channel="EMAIL",
    )
    notif_level_2 = create_notification(
        incident=idem_setup["incident"],
        recipient=idem_setup["user_a"],
        escalation_level=idem_setup["level_2"],
        channel="EMAIL",
    )
    notif_user_b = create_notification(
        incident=idem_setup["incident"],
        recipient=idem_setup["user_b"],
        escalation_level=idem_setup["level_1"],
        channel="EMAIL",
    )
    assert notif_level_1.id != notif_level_2.id
    assert notif_level_1.id != notif_user_b.id
    assert Notification.objects.count() == 3
