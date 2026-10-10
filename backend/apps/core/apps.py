from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"

    def ready(self) -> None:
        # Connects the Celery signal handlers that carry request IDs into tasks.
        from . import logging  # noqa: F401
