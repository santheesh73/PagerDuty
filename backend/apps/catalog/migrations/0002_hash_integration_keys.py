# Expand: add the hashed-key columns and backfill them from the plaintext keys, so every existing
# monitoring integration keeps working. The plaintext column is dropped in 0003.
import hashlib

from django.db import migrations, models


def backfill(apps, schema_editor):
    Service = apps.get_model("catalog", "Service")
    for service in Service.objects.all().only("pk", "integration_key"):
        Service.objects.filter(pk=service.pk).update(
            integration_key_hash=hashlib.sha256(service.integration_key.encode()).hexdigest(),
            integration_key_prefix=service.integration_key[:8],
        )


class Migration(migrations.Migration):
    dependencies = [("catalog", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="service",
            name="integration_key_hash",
            field=models.CharField(editable=False, max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="service",
            name="integration_key_prefix",
            field=models.CharField(
                blank=True, db_default="", default="", editable=False, max_length=12
            ),
        ),
        migrations.AddField(
            model_name="service",
            name="previous_key_hash",
            field=models.CharField(
                blank=True, db_default="", default="", editable=False, max_length=64
            ),
        ),
        migrations.AddField(
            model_name="service",
            name="previous_key_expires_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
