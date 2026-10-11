# Contract: drop the plaintext keys. This deliberately breaks the expand/contract rule (the previous
# release reads this column), because leaving working credentials in the database for one more
# release is the risk this change exists to remove. Deploy it with a stop-then-start, not a rolling
# restart: Events API senders retry, and the gap is the length of the restart. docs/DECISIONS.md.
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("catalog", "0002_hash_integration_keys")]

    operations = [migrations.RemoveField(model_name="service", name="integration_key")]
