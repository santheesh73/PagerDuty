"""The expand step of the channels migration stays safe for a rolling deploy.

The migration linter cannot tell a NOT NULL column that keeps its default from one that drops it,
so this pins the reviewed SQL: every new NOT NULL column keeps a database default, and the indexes
are built concurrently in a separate, non-atomic migration.
"""

import io

import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db


def sql(name: str) -> str:
    out = io.StringIO()
    call_command("sqlmigrate", "notifications", name, stdout=out)
    return out.getvalue()


def test_new_not_null_columns_keep_their_default() -> None:
    statements = sql("0004")
    for column in ("destination", "page_key", "provider_id", "provider_status"):
        assert f'ADD COLUMN "{column}" varchar' in statements
        assert f'ALTER COLUMN "{column}" DROP DEFAULT' not in statements, column
    on_live_table = [
        line
        for line in statements.splitlines()
        if line.startswith("CREATE INDEX") and 'ON "notifications_notification"' in line
    ]
    assert on_live_table == [], "indexes on the live notifications table must be built concurrently"


@pytest.mark.django_db(transaction=True)  # CONCURRENTLY refuses to run inside a transaction
def test_the_indexes_are_built_concurrently() -> None:
    statements = sql("0005")
    assert statements.count("CREATE INDEX CONCURRENTLY") == 2
