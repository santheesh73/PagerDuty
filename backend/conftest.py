import pytest


@pytest.fixture(autouse=True)
def celery_test_isolation(settings):
    """
    Directs Celery tasks created during pytest runs to a dedicated isolated Redis database (db 15).
    This ensures that test tasks with countdowns preserve their async scheduling semantics
    while preventing them from being consumed by the live background worker listening on db 0.
    """
    settings.CELERY_BROKER_URL = "redis://redis:6379/15"
    settings.CELERY_RESULT_BACKEND = "redis://redis:6379/15"
