import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError

from apps.escalation.models import EscalationLevel, EscalationPolicy
from apps.incidents.models import Incident
from apps.services.models import Service
from apps.users.models import Team, TeamMembership

User = get_user_model()


@pytest.fixture
def test_setup():
    team = Team.objects.create(name="Core Team", slug="core-team")
    other_team = Team.objects.create(name="Other Team", slug="other-team")

    user_alice = User.objects.create_user(username="alice_m", email="alice_m@example.com")
    user_bob = User.objects.create_user(username="bob_m", email="bob_m@example.com")
    user_charlie = User.objects.create_user(username="charlie_m", email="charlie_m@example.com")

    TeamMembership.objects.create(user=user_alice, team=team, role=TeamMembership.Role.ENGINEER)
    TeamMembership.objects.create(user=user_bob, team=team, role=TeamMembership.Role.LEAD)
    TeamMembership.objects.create(user=user_charlie, team=other_team, role=TeamMembership.Role.ENGINEER)

    policy = EscalationPolicy.objects.create(name="Core Policy", slug="core-policy", team=team)
    return {
        "team": team,
        "other_team": other_team,
        "alice": user_alice,
        "bob": user_bob,
        "charlie": user_charlie,
        "policy": policy,
    }


@pytest.mark.django_db
def test_escalation_policy_creation_and_fields(test_setup):
    policy = test_setup["policy"]
    assert policy.name == "Core Policy"
    assert policy.team == test_setup["team"]
    assert policy.is_active is True
    assert str(policy) == "Core Policy (Core Team)"


@pytest.mark.django_db
def test_escalation_policy_slug_uniqueness(test_setup):
    with pytest.raises(IntegrityError):
        EscalationPolicy.objects.create(
            name="Duplicate Policy",
            slug=test_setup["policy"].slug,
            team=test_setup["team"],
        )


@pytest.mark.django_db
def test_escalation_level_current_on_call_valid(test_setup):
    level = EscalationLevel.objects.create(
        policy=test_setup["policy"],
        order=1,
        target_type=EscalationLevel.TargetType.CURRENT_ON_CALL,
        wait_minutes=15,
    )
    assert level.order == 1
    assert level.target_type == EscalationLevel.TargetType.CURRENT_ON_CALL
    assert level.target_user is None
    assert level.wait_minutes == 15


@pytest.mark.django_db
def test_escalation_level_user_target_valid(test_setup):
    level = EscalationLevel.objects.create(
        policy=test_setup["policy"],
        order=2,
        target_type=EscalationLevel.TargetType.USER,
        target_user=test_setup["bob"],
        wait_minutes=30,
    )
    assert level.target_user == test_setup["bob"]
    assert level.wait_minutes == 30


@pytest.mark.django_db
def test_escalation_level_unique_policy_order(test_setup):
    EscalationLevel.objects.create(
        policy=test_setup["policy"],
        order=1,
        target_type=EscalationLevel.TargetType.CURRENT_ON_CALL,
        wait_minutes=5,
    )
    with pytest.raises((IntegrityError, ValidationError)):
        EscalationLevel.objects.create(
            policy=test_setup["policy"],
            order=1,
            target_type=EscalationLevel.TargetType.USER,
            target_user=test_setup["alice"],
            wait_minutes=10,
        )


@pytest.mark.django_db
def test_escalation_level_order_must_be_positive(test_setup):
    level = EscalationLevel(
        policy=test_setup["policy"],
        order=0,
        target_type=EscalationLevel.TargetType.CURRENT_ON_CALL,
        wait_minutes=5,
    )
    with pytest.raises(ValidationError) as exc:
        level.save()
    assert "order" in exc.value.message_dict


@pytest.mark.django_db
def test_escalation_level_wait_minutes_non_negative(test_setup):
    level = EscalationLevel(
        policy=test_setup["policy"],
        order=1,
        target_type=EscalationLevel.TargetType.CURRENT_ON_CALL,
        wait_minutes=-5,
    )
    with pytest.raises(ValidationError) as exc:
        level.save()
    assert "wait_minutes" in exc.value.message_dict


@pytest.mark.django_db
def test_escalation_level_user_target_requires_target_user(test_setup):
    level = EscalationLevel(
        policy=test_setup["policy"],
        order=1,
        target_type=EscalationLevel.TargetType.USER,
        target_user=None,
        wait_minutes=10,
    )
    with pytest.raises(ValidationError) as exc:
        level.save()
    assert "target_user" in exc.value.message_dict


@pytest.mark.django_db
def test_escalation_level_user_target_requires_active_user(test_setup):
    inactive_user = User.objects.create_user(username="inactive_u", is_active=False)
    TeamMembership.objects.create(user=inactive_user, team=test_setup["team"], role=TeamMembership.Role.ENGINEER)

    level = EscalationLevel(
        policy=test_setup["policy"],
        order=1,
        target_type=EscalationLevel.TargetType.USER,
        target_user=inactive_user,
        wait_minutes=10,
    )
    with pytest.raises(ValidationError) as exc:
        level.save()
    assert "target_user" in exc.value.message_dict


@pytest.mark.django_db
def test_escalation_level_user_target_cross_team_rejected(test_setup):
    # Charlie is a member of other_team, not policy.team
    level = EscalationLevel(
        policy=test_setup["policy"],
        order=1,
        target_type=EscalationLevel.TargetType.USER,
        target_user=test_setup["charlie"],
        wait_minutes=10,
    )
    with pytest.raises(ValidationError) as exc:
        level.save()
    assert "target_user" in exc.value.message_dict


@pytest.mark.django_db
def test_escalation_level_current_on_call_rejects_target_user(test_setup):
    level = EscalationLevel(
        policy=test_setup["policy"],
        order=1,
        target_type=EscalationLevel.TargetType.CURRENT_ON_CALL,
        target_user=test_setup["alice"],
        wait_minutes=10,
    )
    with pytest.raises(ValidationError) as exc:
        level.save()
    assert "target_user" in exc.value.message_dict


@pytest.mark.django_db
def test_protected_deletion_policy_referenced_by_service(test_setup):
    Service.objects.create(
        name="Billing API",
        slug="billing-api",
        team=test_setup["team"],
        escalation_policy=test_setup["policy"],
    )
    with pytest.raises(ProtectedError):
        test_setup["policy"].delete()


@pytest.mark.django_db
def test_protected_deletion_level_referenced_by_incident(test_setup):
    service = Service.objects.create(
        name="Billing API",
        slug="billing-api",
        team=test_setup["team"],
        escalation_policy=test_setup["policy"],
    )
    level = EscalationLevel.objects.create(
        policy=test_setup["policy"],
        order=1,
        target_type=EscalationLevel.TargetType.CURRENT_ON_CALL,
        wait_minutes=10,
    )
    Incident.objects.create(
        service=service,
        title="Payment outage",
        fingerprint="fp-test-protected",
        current_escalation_level=level,
    )
    with pytest.raises(ProtectedError):
        level.delete()
