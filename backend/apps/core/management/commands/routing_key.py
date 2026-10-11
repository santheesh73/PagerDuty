from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.models import Service


class Command(BaseCommand):
    help = (
        "Issue a new integration (routing) key for a service and print it. Keys are stored only as "
        "hashes, so the old one cannot be shown; it keeps working for INTEGRATION_KEY_GRACE_HOURS. "
        "Used by `make send-alert`, the drills and CI."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("service", help="Service name, e.g. checkout-api")

    def handle(self, *args: Any, **options: Any) -> None:
        service = Service.objects.filter(name=options["service"]).first()
        if service is None:
            raise CommandError(f"No service named {options['service']!r}. Run `make seed`?")
        from apps.catalog.actions import rotate_integration_key

        self.stdout.write(rotate_integration_key(service))
