from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.models import Service


class Command(BaseCommand):
    help = "Print a service's integration (routing) key. Used by `make send-alert`."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("service", help="Service name, e.g. checkout-api")

    def handle(self, *args: Any, **options: Any) -> None:
        service = Service.objects.filter(name=options["service"]).first()
        if service is None:
            raise CommandError(f"No service named {options['service']!r}. Run `make seed`?")
        self.stdout.write(service.integration_key)
