"""Settings for `manage.py lintmigrations` (CI and `make lint-migrations`).

django-migration-linter is a dev-only dependency, so its app is registered here, not in base.
"""

from .dev import *  # noqa: F403
from .dev import INSTALLED_APPS

INSTALLED_APPS = [*INSTALLED_APPS, "django_migration_linter"]
