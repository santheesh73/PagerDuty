"""Transaction-scoped Postgres advisory locks.

An advisory lock serialises work that has no row to lock yet, such as "open an incident for this
key unless one is already open". It is released automatically at commit or rollback, is shared by
every process talking to the database, and never outlives the transaction.
"""

from django.db import connection


def advisory_xact_lock(namespace: str, *parts: object) -> None:
    """Block until this transaction holds the lock for `namespace` + `parts`. Needs atomic()."""
    if not connection.in_atomic_block:
        raise RuntimeError("advisory_xact_lock must be called inside transaction.atomic()")
    key = ":".join([namespace, *map(str, parts)])
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [key])
