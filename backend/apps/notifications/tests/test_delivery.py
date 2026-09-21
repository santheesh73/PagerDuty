import pytest
from django.contrib.auth import get_user_model

from apps.incidents.models import Incident
from apps.notifications.exceptions import NotificationDeliveryError
from apps.notifications.models import Notification
from apps.notifications.providers import SimulatedEmailProvider, get_notification_provider
from apps.services.models import Service
from apps.users.models import Team

User = get_user_model()


@pytest.fixture
def delivery_setup():
    team = Team.objects.create(name="Delivery Team", slug="delivery-team")
    user = User.objects.create_user(username="deliv_user", email="deliv@example.com")
    service = Service.objects.create(name="Delivery Service", slug="delivery-svc", team=team)
    incident = Incident.objects.create(service=service, title="Delivery Test", fingerprint="fp-deliv-1")
    notif = Notification.objects.create(incident=incident, recipient=user, dedupe_key="deliv-key-1")
    return notif


@pytest.mark.django_db
def test_simulated_email_provider_success(delivery_setup):
    provider = SimulatedEmailProvider()
    result = provider.send(delivery_setup)
    assert result is True


@pytest.mark.django_db
def test_simulated_email_provider_fault_injection(delivery_setup):
    provider = SimulatedEmailProvider()
    provider.force_failure = True
    try:
        with pytest.raises(NotificationDeliveryError) as exc:
            provider.send(delivery_setup)
        assert "Simulated email delivery failed" in str(exc.value)
    finally:
        provider.force_failure = False


def test_get_notification_provider_factory():
    provider = get_notification_provider("EMAIL")
    assert isinstance(provider, SimulatedEmailProvider)

    with pytest.raises(ValueError):
        get_notification_provider("UNSUPPORTED_CARRIER")
