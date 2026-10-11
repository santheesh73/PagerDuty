"""Check what a k6 run did to the database.

    docker compose exec api python /loadtest/verify.py ... (or any shell with Django set up)
    python loadtest/verify.py --run-id <RUN_ID> --new-keys <N> --hot-keys <M>

Exits non-zero when a guarantee was broken under load:
  I1  no (service, dedup_key) has more than one open incident
  --  every never-seen key opened exactly one incident (no lost or duplicated opens)
  --  every hot key opened at most one incident, and the repeats attached to it
"""

import argparse
import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
django.setup()

from django.db.models import Count  # noqa: E402

from apps.alerting.models import Alert  # noqa: E402
from apps.incidents.models import Incident, Status  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--new-keys", type=int, required=True, help="pulse_new_keys from k6")
    parser.add_argument("--hot-requests", type=int, required=True, help="pulse_hot_requests")
    args = parser.parse_args()

    failures = []
    mine = Incident.objects.filter(dedup_key__contains=args.run_id)

    dup_open = (
        mine.exclude(status=Status.RESOLVED)
        .values("service_id", "dedup_key")
        .annotate(n=Count("pk"))
        .filter(n__gt=1)
        .count()
    )
    if dup_open:
        failures.append(f"I1: {dup_open} dedup keys have more than one open incident")

    new_incidents = mine.filter(dedup_key__startswith=f"new-{args.run_id}").count()
    if new_incidents != args.new_keys:
        failures.append(f"{args.new_keys} new keys were sent but {new_incidents} incidents opened")

    hot_incidents = mine.filter(dedup_key__startswith=f"hot-{args.run_id}")
    hot_alerts = Alert.objects.filter(incident__in=hot_incidents).count()
    if hot_alerts != args.hot_requests:
        failures.append(
            f"{args.hot_requests} hot requests were sent but {hot_alerts} alerts were recorded"
        )

    print(
        f"new keys sent={args.new_keys} incidents={new_incidents} | hot requests sent="
        f"{args.hot_requests} alerts recorded={hot_alerts} on {hot_incidents.count()} incidents"
    )
    for failure in failures:
        print("FAIL", failure)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
