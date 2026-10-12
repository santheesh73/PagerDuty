from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("notifications", "0005_notification_indexes_concurrently")]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="next_attempt_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
