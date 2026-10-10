"""Settings shared by every environment. Anything environment-specific reads from os.environ."""

import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from kombu import Queue

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = os.environ.get("SECRET_KEY", "")
DEBUG = False
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "apps.core",
    "apps.accounts",
    "apps.catalog",
    "apps.alerting",
    "apps.incidents",
    "apps.escalations",
    "apps.schedules",
    "apps.notifications",
    "apps.analytics",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "apps.core.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": dj_database_url.parse(
        os.environ.get("DATABASE_URL", "postgres://pulse:pulse@localhost:5432/pulse"),
        conn_max_age=60,
        conn_health_checks=True,
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        # Redis is disposable: a cache outage must degrade throttling, not fail requests.
        "OPTIONS": {"socket_connect_timeout": 1, "socket_timeout": 1},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Auth / sessions -------------------------------------------------------
# The SPA is served from the same site (Vite proxy in dev, one origin in prod), so
# cookie sessions + CSRF are the simplest secure option: no tokens in localStorage.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # the SPA reads it to echo X-CSRFToken
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "http://localhost:5173")
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOW_CREDENTIALS = True

# --- DRF -------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "EXCEPTION_HANDLER": "apps.core.errors.exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "login": os.environ.get("THROTTLE_LOGIN", "10/min"),
        "events": os.environ.get("THROTTLE_EVENTS", "120/min"),
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Pulse API",
    "DESCRIPTION": "Incident orchestration: Events ingest, incidents, escalation, on-call.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "apps.core.schema.require_response_fields",
    ],
    "ENUM_NAME_OVERRIDES": {
        "IncidentStatusEnum": "apps.incidents.models.Status",
        "AlertStatusEnum": "apps.alerting.models.Alert.Status",
        "NotificationStatusEnum": "apps.notifications.models.Notification.Status",
        "ServiceModeEnum": "apps.catalog.models.Service.Mode",
    },
}

# --- Celery ----------------------------------------------------------------
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = None  # results are never read; state lives in Postgres
CELERY_TASK_IGNORE_RESULT = True
CELERY_TIMEZONE = "UTC"
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
# A worker crash mid-task must re-deliver the message, not lose a page.
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
# Paging must never queue behind a notification backlog, so escalations get their own queue.
CELERY_TASK_QUEUES = (Queue("escalations"), Queue("notifications"), Queue("default"))
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {
    "apps.escalations.tasks.*": {"queue": "escalations"},
    "apps.notifications.tasks.*": {"queue": "notifications"},
}
CELERY_BEAT_SCHEDULE: dict[str, dict] = {
    "sweep-due-escalations": {
        "task": "apps.escalations.tasks.sweep_due_escalations",
        "schedule": timedelta(seconds=30),
    },
    "expire-service-modes": {
        "task": "apps.catalog.tasks.expire_service_modes",
        "schedule": timedelta(seconds=60),
    },
    "sweep-stuck-notifications": {
        "task": "apps.notifications.tasks.sweep_stuck_notifications",
        "schedule": timedelta(minutes=5),
    },
}

# --- Email -----------------------------------------------------------------
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "pulse@localhost")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")

# --- Logging ---------------------------------------------------------------
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "apps.core.logging.RequestIDFilter"}},
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
            "rename_fields": {"asctime": "ts", "levelname": "level", "name": "logger"},
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["request_id"],
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
        "celery": {"level": "INFO"},
    },
}
