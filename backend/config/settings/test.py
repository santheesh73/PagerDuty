import os

# pytest-django holds one transaction open for a whole test; do not let the idle limit kill it.
os.environ.setdefault("DB_IDLE_IN_TX_TIMEOUT_MS", "0")

from .base import *  # noqa: F403

SECRET_KEY = "test-only-key"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast fixtures
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
LOGGING = {"version": 1, "disable_existing_loggers": False}
# Engine tests call actions directly; on_commit dispatch goes nowhere unless a test opts in.
CELERY_TASK_ALWAYS_EAGER = False
CELERY_BROKER_URL = "memory://"
