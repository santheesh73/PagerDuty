# Built CONCURRENTLY so adding them never takes a write lock on notifications (paging keeps
# working during the deploy). Concurrent index builds cannot run in a transaction, hence
# atomic = False. See docs/DATA_SAFETY.md, "Migrations on a live database".
from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False

    dependencies = [("notifications", "0004_channels_rules_contacts")]

    operations = [
        AddIndexConcurrently(
            model_name="notification",
            index=models.Index(
                fields=["incident", "page_key"], name="notification_page_key_idx"
            ),
        ),
        AddIndexConcurrently(
            model_name="notification",
            index=models.Index(
                condition=models.Q(("provider_id", ""), _negated=True),
                fields=["provider_id"],
                name="notification_provider_idx",
            ),
        ),
    ]
