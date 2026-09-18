from config.celery import app as celery_app
from config.celery import health_ping


def test_celery_configuration():
    """Verify Celery application is configured with expected settings."""
    assert celery_app.main == "incident_platform"
    assert celery_app.conf.timezone == "UTC"
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"


def test_celery_health_ping_task_registered():
    """Verify Celery task registration includes the health_ping smoke task."""
    assert "health_ping" in celery_app.tasks


def test_celery_health_ping_execution():
    """Verify the health_ping smoke task executes directly and returns 'pong'."""
    result = health_ping()
    assert result == "pong"
