import pytest
from django.db import IntegrityError

from apps.services.models import Service
from apps.users.models import Team


@pytest.fixture
def team():
    return Team.objects.create(name="Backend Team", slug="backend")


@pytest.mark.django_db
def test_create_valid_service(team):
    """Verify Service creation and string representation."""
    service = Service.objects.create(
        name="Payment API",
        slug="payment-api",
        description="Processes credit card payments",
        team=team,
        status=Service.Status.HEALTHY,
    )
    assert service.id is not None
    assert service.name == "Payment API"
    assert service.slug == "payment-api"
    assert service.team == team
    assert service.status == Service.Status.HEALTHY
    assert service.is_active is True
    assert service.created_at is not None
    assert service.updated_at is not None
    assert str(service) == "Payment API"


@pytest.mark.django_db
def test_service_requires_team():
    """Verify that a Service cannot be created without an associated Team."""
    with pytest.raises(IntegrityError):
        Service.objects.create(
            name="Orphan Service",
            slug="orphan-service",
            team=None,
        )


@pytest.mark.django_db
def test_service_slug_uniqueness(team):
    """Verify database-level unique constraint on service slug."""
    Service.objects.create(name="Service A", slug="unique-slug", team=team)
    with pytest.raises(IntegrityError):
        Service.objects.create(name="Service B", slug="unique-slug", team=team)


@pytest.mark.django_db
def test_service_status_choices(team):
    """Verify status choices can be set."""
    service = Service.objects.create(
        name="Auth API",
        slug="auth-api",
        team=team,
        status=Service.Status.DEGRADED,
    )
    assert service.status == "DEGRADED"

    service.status = Service.Status.DOWN
    service.save()
    service.refresh_from_db()
    assert service.status == "DOWN"


@pytest.mark.django_db
def test_service_inactive_toggle(team):
    """Verify active/inactive state toggle."""
    service = Service.objects.create(
        name="Legacy Service",
        slug="legacy",
        team=team,
        is_active=False,
    )
    assert service.is_active is False
