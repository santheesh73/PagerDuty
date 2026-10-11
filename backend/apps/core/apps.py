from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"

    def ready(self) -> None:
        from django.core.signals import request_finished

        # Importing `logging` connects the Celery signal handlers that carry request IDs into tasks.
        from . import logging, tick  # noqa: F401

        # Demo mode only, and off unless DEMO_SELF_TICK_SECONDS is set: see apps/core/tick.py.
        request_finished.connect(tick.self_tick, dispatch_uid="pulse-self-tick")
