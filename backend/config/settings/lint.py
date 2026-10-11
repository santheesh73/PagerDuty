"""Settings for `manage.py lintmigrations` (CI and `make lint-migrations`).

django-migration-linter is a dev-only dependency, so its app is registered here, not in base.
"""

from .dev import *  # noqa: F403
from .dev import INSTALLED_APPS

INSTALLED_APPS = [*INSTALLED_APPS, "django_migration_linter"]

# Reviewed by hand, and pinned by apps/notifications/tests/test_migration_0004.py: the new
# notification columns are added with a *retained* DEFAULT '' (db_default), which Postgres 11+
# applies as metadata only and which the previous release can insert around during a rolling
# deploy. The linter flags any NOT NULL column regardless of a kept default.
# 0003_drop_plaintext_integration_key drops a column the previous release reads, on purpose: it
# removes stored credentials (see the migration and docs/DECISIONS.md).
MIGRATION_LINTER_OPTIONS = {
    "ignore_name": ["0004_channels_rules_contacts", "0003_drop_plaintext_integration_key"]
}
