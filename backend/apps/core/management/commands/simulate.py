"""Run the seeded fault-injection simulator against a throwaway test database.

python manage.py simulate --seed 7 --operations 600
python manage.py simulate --seeds 20      # seeds 1..20, stop at the first failure
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.core.simulation import Simulation, SimulationFailure


class Command(BaseCommand):
    help = "Run the fault-injection simulator (never touches the real database)."

    def add_arguments(self, parser):
        parser.add_argument("--seed", type=int, default=20261011)
        parser.add_argument("--seeds", type=int, help="run seeds 1..N instead of --seed")
        parser.add_argument("--operations", type=int, default=600)

    def handle(self, *args, seed, seeds, operations, **options):
        logging.disable(logging.CRITICAL)  # injected faults log expected errors
        run = list(range(1, seeds + 1)) if seeds else [seed]
        # The simulator creates and commits real rows, so it gets its own database.
        old_name = connection.settings_dict["NAME"]
        connection.creation.create_test_db(verbosity=0, autoclobber=True)
        try:
            for current in run:
                self.stdout.write(f"seed {current} ...", ending=" ")
                try:
                    report = Simulation(current, operations=operations).run()
                except SimulationFailure as failure:
                    self.stdout.write(self.style.ERROR("FAILED"))
                    raise CommandError(str(failure)) from failure
                self.stdout.write(self.style.SUCCESS("ok"))
                self.stdout.write("  " + report.summary())
                self._wipe()
        finally:
            connection.creation.destroy_test_db(old_name, verbosity=0)

    @staticmethod
    def _wipe() -> None:
        from django.core.management import call_command

        call_command("flush", interactive=False, verbosity=0)
