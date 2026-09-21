import pytest

from apps.alerts.models import Alert
from apps.alerts.triage import build_alert_fingerprint
from apps.services.models import Service
from apps.users.models import Team


@pytest.fixture
def service():
    team = Team.objects.create(name="Backend Team", slug="backend")
    return Service.objects.create(name="Payment API", slug="payment-api", team=team)


@pytest.mark.django_db
def test_create_valid_alert(service):
    """Verify Alert model persistence and relationships."""
    fp = build_alert_fingerprint(service.id, "prometheus", "Disk 95% full")
    alert = Alert.objects.create(
        service=service,
        severity=Alert.Severity.CRITICAL,
        message="Disk 95% full",
        source="prometheus",
        fingerprint=fp,
        metadata={"host": "worker-1"},
    )
    assert alert.id is not None
    assert alert.service == service
    assert alert.severity == "CRITICAL"
    assert alert.source == "prometheus"
    assert alert.message == "Disk 95% full"
    assert alert.fingerprint == fp
    assert alert.metadata["host"] == "worker-1"
    assert alert.received_at is not None
    assert alert.created_at is not None
    assert "[CRITICAL] Payment API: Disk 95% full" in str(alert)
