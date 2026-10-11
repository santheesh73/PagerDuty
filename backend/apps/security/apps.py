from django.apps import AppConfig


class SecurityConfig(AppConfig):
    name = "apps.security"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from . import sessions  # noqa: F401 - connects the login/logout signal receivers
