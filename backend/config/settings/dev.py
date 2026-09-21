"""Development settings for Incident Management Platform."""
import os

from .base import *  # noqa: F403
from .base import BASE_DIR, CORS_ALLOWED_ORIGINS

DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() in ("true", "1", "yes")

# In development, allow localhost CORS by default if not set
if "localhost" not in " ".join(CORS_ALLOWED_ORIGINS):
    CORS_ALLOWED_ORIGINS.extend([
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ])

# Local developer convenience fallback: Only enable SQLite when explicitly requested
# via DJANGO_USE_SQLITE=True (e.g., local unit tests without Docker/PostgreSQL running).
# Docker runs always use PostgreSQL.
if os.environ.get("DJANGO_USE_SQLITE", "False").lower() in ("true", "1", "yes"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "OPTIONS": {
                "timeout": 20,
            },
        }
    }
