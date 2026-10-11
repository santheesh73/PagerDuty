from django.conf import settings


def test_the_suite_runs_on_test_settings_whatever_the_environment_says() -> None:
    """`.env` exports DJANGO_SETTINGS_MODULE=config.settings.dev, and an environment variable
    beats pytest.ini. Under dev settings the suite is several times slower (real password
    hashing) and can enqueue onto a live broker, so pytest pins the module on the command line."""
    assert settings.SETTINGS_MODULE == "config.settings.test"
