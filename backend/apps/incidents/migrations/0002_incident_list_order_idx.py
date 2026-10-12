# Built CONCURRENTLY so it never takes a write lock on incidents (ingest keeps working during the
# deploy); concurrent builds cannot run in a transaction, hence atomic = False. See
# docs/DATA_SAFETY.md, "Migrations on a live database".
from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False

    dependencies = [("incidents", "0001_initial")]

    operations = [
        AddIndexConcurrently(
            model_name="incident",
            index=models.Index(fields=["-triggered_at", "-id"], name="incident_list_order_idx"),
        ),
    ]
