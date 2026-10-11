"""Existing integrations keep working across the switch to hashed keys (migrations 0002/0003)."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.catalog.actions import service_for_key


@pytest.mark.django_db(transaction=True)
def test_a_key_issued_before_hashing_still_authenticates_after_the_migration() -> None:
    executor = MigrationExecutor(connection)
    old_state = [("catalog", "0001_initial")]
    executor.migrate(old_state)
    apps = executor.loader.project_state(old_state).apps
    Team = apps.get_model("accounts", "Team")
    Policy = apps.get_model("escalations", "EscalationPolicy")
    Service = apps.get_model("catalog", "Service")
    team = Team.objects.create(name="Legacy", slug="legacy-team")
    policy = Policy.objects.create(team=team, name="Legacy policy")
    legacy_key = "a" * 64
    Service.objects.create(
        team=team, name="legacy", escalation_policy=policy, integration_key=legacy_key
    )

    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())

    service = service_for_key(legacy_key)
    assert service is not None
    assert service.name == "legacy"
    assert service.integration_key_prefix == "aaaaaaaa"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'catalog_service'"
        )
        columns = {row[0] for row in cursor.fetchall()}
    assert "integration_key" not in columns, "the plaintext column must be gone"
