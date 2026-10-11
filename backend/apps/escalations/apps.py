from django.apps import AppConfig


class EscalationsConfig(AppConfig):
    name = "apps.escalations"
    label = "escalations"

    def ready(self) -> None:
        from . import guards

        guards.install()
