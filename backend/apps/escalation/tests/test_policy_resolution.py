import pytest
from apps.escalation.models import EscalationPolicy
from apps.escalation.services import find_escalation_policy
from apps.services.models import Service
from apps.users.models import Team


@pytest.fixture
def resolution_setup():
    team_a = Team.objects.create(name="Team Alpha", slug="team-alpha")
    team_b = Team.objects.create(name="Team Beta", slug="team-beta")

    policy_a = EscalationPolicy.objects.create(name="Policy Alpha", slug="policy-alpha", team=team_a, is_active=True)
    policy_b = EscalationPolicy.objects.create(name="Policy Beta", slug="policy-beta", team=team_b, is_active=True)
    inactive_policy = EscalationPolicy.objects.create(name="Inactive Policy", slug="policy-inactive", team=team_a, is_active=False)

    service_a = Service.objects.create(name="Service Alpha", slug="svc-alpha", team=team_a, escalation_policy=policy_a)
    service_no_policy = Service.objects.create(name="Service Raw", slug="svc-raw", team=team_a, escalation_policy=None)

    return {
        "team_a": team_a,
        "team_b": team_b,
        "policy_a": policy_a,
        "policy_b": policy_b,
        "inactive_policy": inactive_policy,
        "service_a": service_a,
        "service_no_policy": service_no_policy,
    }


@pytest.mark.django_db
def test_find_escalation_policy_success(resolution_setup):
    service = resolution_setup["service_a"]
    policy = find_escalation_policy(service)
    assert policy is not None
    assert policy.id == resolution_setup["policy_a"].id


@pytest.mark.django_db
def test_find_escalation_policy_missing_returns_none(resolution_setup):
    service = resolution_setup["service_no_policy"]
    policy = find_escalation_policy(service)
    assert policy is None


@pytest.mark.django_db
def test_find_escalation_policy_inactive_returns_none(resolution_setup):
    service = resolution_setup["service_a"]
    service.escalation_policy = resolution_setup["inactive_policy"]
    service.save()

    policy = find_escalation_policy(service)
    assert policy is None


@pytest.mark.django_db
def test_find_escalation_policy_mismatched_team_returns_none(resolution_setup):
    # Service A (Team Alpha) points to Policy B (Team Beta)
    service = resolution_setup["service_a"]
    service.escalation_policy = resolution_setup["policy_b"]
    service.save()

    policy = find_escalation_policy(service)
    assert policy is None


@pytest.mark.django_db
def test_find_escalation_policy_handles_none_service():
    assert find_escalation_policy(None) is None
