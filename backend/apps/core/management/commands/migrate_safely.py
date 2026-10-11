"""`migrate`, serialised across processes by a Postgres advisory lock.

Plain `manage.py migrate` is not safe to run twice at once: two processes on a fresh database
both try to create the same tables and one dies with `duplicate key ... pg_type_typname_nsp_index`
(reproduced: 3 of 4 concurrent runs failed, three rounds out of three). Starting several API
replicas at once does exactly that. Holding a session-level advisory lock makes the others wait
and then find nothing left to do.

Waiters *poll* `pg_try_advisory_lock` instead of blocking in `pg_advisory_lock`. A blocked call is
an open transaction, and `CREATE INDEX CONCURRENTLY` (used by non-atomic migrations) waits for every
open transaction to finish, so the migrating process and the waiters deadlocked (reproduced: one
process killed with `deadlock detected`, the rest then tripping over its half-built index). Each
poll is an instant statement, so waiters hold nothing between tries.
"""

import time

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection

# Arbitrary, stable, namespaced away from the per-incident locks in apps/core/locks.py.
LOCK_KEY = 0x50554C5345  # "PULSE"
POLL_SECONDS = 0.5


class Command(BaseCommand):
    help = "Run migrate while holding a cluster-wide advisory lock."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--lock-timeout-ms",
            type=int,
            default=10000,
            help="lock_timeout for the migration itself (0 = wait forever); the wait for the "
            "advisory lock is never limited",
        )

    def handle(self, *args, **options) -> None:
        with connection.cursor() as cursor:
            # Waiting for another replica's migration must not be cut short by the
            # statement/lock timeouts that protect request handling.
            cursor.execute("SET statement_timeout = 0")
            cursor.execute("SET lock_timeout = 0")
            waited = 0.0
            while True:
                cursor.execute("SELECT pg_try_advisory_lock(%s)", [LOCK_KEY])
                if cursor.fetchone()[0]:
                    break
                if waited == 0:
                    self.stdout.write("Another process is migrating; waiting for it to finish.")
                time.sleep(POLL_SECONDS)
                waited += POLL_SECONDS
            try:
                # From here a migration that cannot get its table lock fails fast instead of
                # queueing behind a long transaction and blocking all traffic behind itself.
                cursor.execute(f"SET lock_timeout = {int(options['lock_timeout_ms'])}")
                call_command("migrate", interactive=False, verbosity=options["verbosity"])
            finally:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK_KEY])
