"""`manage.py selfcheck`: exit 0 only if Pulse is doing its job (see apps/core/selfcheck.py).

Run it from cron or an external monitor. With --ping it also hits HEARTBEAT_URL on success,
so a host cron can serve as a second dead-man's switch independent of Celery Beat.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.core import heartbeat, selfcheck


class Command(BaseCommand):
    help = "Check the database, escalation sweeper, notification delivery and Beat heartbeat."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--ping", action="store_true", help="ping HEARTBEAT_URL on success")
        parser.add_argument("--no-beat", action="store_true", help="skip the Beat heartbeat check")

    def handle(self, *args, **options) -> None:
        checks = selfcheck.run(include_beat=not options["no_beat"])
        for check in checks:
            self.stdout.write(f"{'ok  ' if check.ok else 'FAIL'} {check.name}: {check.detail}")
        if not all(c.ok for c in checks):
            raise CommandError("selfcheck failed")
        if options["ping"]:
            self.stdout.write("pinged" if heartbeat.ping_external() else "ping skipped/failed")
