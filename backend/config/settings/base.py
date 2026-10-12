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
    "apps.security",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "apps.core.middleware.RequestIDMiddleware",
    "apps.core.middleware.ObservabilityMiddleware",
    "apps.core.api_errors.BodySizeLimitMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.security.middleware.MfaEnrolmentMiddleware",
    "apps.core.demo.DemoAccountGuardMiddleware",
    "apps.core.idempotency.IdempotencyMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "apps.security.middleware.SecurityHeadersMiddleware",
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
                "django.template.context_processors.csp",
            ],
        },
    },
]


def _db_session_options() -> str:
    """Postgres session limits, so one bad query or client cannot wedge the whole database.

    * statement_timeout: a runaway query is cancelled instead of pinning a worker (15 s; every
      request and task here is small, indexed work).
    * lock_timeout: waiting for a row/table lock gives up (5 s) instead of queueing forever.
    * idle_in_transaction_session_timeout: a client that opened a transaction and went quiet is
      dropped (60 s) because it is holding locks. Delivery deliberately sends with no
      transaction open, so a legitimate path never idles in one.

    Set any of the DB_*_MS variables to 0 to omit that limit. Poolers in transaction mode
    (PgBouncer, Neon's pooled endpoint) reject startup options: set all three to 0 there.
    """
    limits = (
        ("statement_timeout", "DB_STATEMENT_TIMEOUT_MS", 15_000),
        ("lock_timeout", "DB_LOCK_TIMEOUT_MS", 5_000),
        ("idle_in_transaction_session_timeout", "DB_IDLE_IN_TX_TIMEOUT_MS", 60_000),
    )
    parts = []
    for name, variable, default in limits:
        milliseconds = int(os.environ.get(variable, default))
        if milliseconds > 0:
            parts.append(f"-c {name}={milliseconds}")
    return " ".join(parts)


DATABASES = {
    "default": dj_database_url.parse(
        os.environ.get("DATABASE_URL", "postgres://pulse:pulse@localhost:5432/pulse"),
        # Persistent connections avoid a TCP+auth handshake per request; health checks drop a
        # connection the server closed. Total = gunicorn workers + Celery processes (about 10
        # by default), far under Postgres' 100. Use 0 behind a transaction-mode pooler.
        conn_max_age=int(os.environ.get("DB_CONN_MAX_AGE", "60")),
        conn_health_checks=True,
    )
}
if _session_options := _db_session_options():
    DATABASES["default"].setdefault("OPTIONS", {})["options"] = _session_options
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

# Applied wherever a person chooses a password (reset, change, createsuperuser). Length is what
# matters most; the common-password list stops the usual suspects. The seeded demo accounts are
# created directly and are documented as demo-only.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_RESET_TIMEOUT = 60 * 60  # reset links expire after an hour

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

# 1 MiB for any request body (nginx enforces the same at the edge). The Events API has its own,
# smaller, documented limit (core/limits.py).
DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Auth / sessions -------------------------------------------------------
# The SPA is served from the same site (Vite proxy in dev, one origin in prod), so
# cookie sessions + CSRF are the simplest secure option: no tokens in localStorage.
SESSION_COOKIE_HTTPONLY = True
# An absolute lifetime, not a sliding one: a stolen cookie dies on schedule however busy it is.
SESSION_COOKIE_AGE = int(os.environ.get("SESSION_HOURS", "12")) * 3600
# Team admins (and staff) must enrol TOTP before they can do anything else. Off for local dev and
# the demo stacks, on in production settings unless explicitly disabled.
REQUIRE_MFA_FOR_ADMINS = env_bool("REQUIRE_MFA_FOR_ADMINS", False)
# Per-account sign-in lockout, on top of the per-address throttle: this many failures in the
# window and the account refuses passwords until it ends (whoever is guessing, from wherever).
LOGIN_LOCKOUT_FAILURES = int(os.environ.get("LOGIN_LOCKOUT_FAILURES", "10"))
LOGIN_LOCKOUT_SECONDS = int(os.environ.get("LOGIN_LOCKOUT_SECONDS", "900"))
# Wrong two-factor codes per account before the code step locks, across password steps.
MFA_LOCKOUT_FAILURES = int(os.environ.get("MFA_LOCKOUT_FAILURES", "10"))
MFA_LOCKOUT_SECONDS = int(os.environ.get("MFA_LOCKOUT_SECONDS", "900"))
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # the SPA reads it to echo X-CSRFToken
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "http://localhost:5173")
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "")
CORS_ALLOW_CREDENTIALS = True
from corsheaders.defaults import default_headers  # noqa: E402

CORS_ALLOW_HEADERS = (*default_headers, "idempotency-key")

# --- DRF -------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "EXCEPTION_HANDLER": "apps.core.errors.exception_handler",
    # How many reverse proxies we trust to append to X-Forwarded-For. DRF then reads the
    # client address that many entries from the right, so a client-sent prefix can't pick
    # its own throttle bucket. Unset (None) trusts the whole header: only right when
    # nothing sits in front of Django. The compose files set 1 (their nginx).
    "NUM_PROXIES": int(os.environ["NUM_PROXIES"]) if os.environ.get("NUM_PROXIES") else None,
    "DEFAULT_THROTTLE_RATES": {
        "login": os.environ.get("THROTTLE_LOGIN", "10/min"),
        "events": os.environ.get("THROTTLE_EVENTS", "120/min"),
        "phone_code": os.environ.get("THROTTLE_PHONE_CODE", "5/hour"),
        "mfa": os.environ.get("THROTTLE_MFA", "10/min"),
        "password_reset": os.environ.get("THROTTLE_PASSWORD_RESET", "10/hour"),
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Pulse API",
    "DESCRIPTION": "Incident orchestration: Events ingest, incidents, escalation, on-call.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # An exact release, never @latest: this script runs on the same origin as the session cookie.
    "SWAGGER_UI_DIST": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14",
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
        "UrgencyEnum": "apps.incidents.models.Urgency",
        "ChannelEnum": "apps.notifications.models.Notification.Channel",
        "RuleUrgencyEnum": "apps.notifications.models.NotificationRule.Urgency",
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
# Redis re-delivers an unacked message after this long. Recovery of a dead worker's page does NOT
# depend on it (the 60 s stuck-notification sweep re-drives within ~2.5 minutes), so it only has
# to exceed the longest legitimate ETA wait to avoid pointless redelivery of escalation timers;
# those are minutes, and the DB timer is authoritative anyway. Explicit rather than the default.
# Socket timeouts bound a broker that accepts connections and never answers (a hung Redis): with
# none, the publish in `on_commit` blocked the request for minutes after the incident was already
# committed. A failed publish is logged and the sweeper re-drives it (core/dispatch.py).
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "visibility_timeout": 3600,
    "socket_connect_timeout": 2,
    "socket_timeout": 5,
}
CELERY_TASK_PUBLISH_RETRY_POLICY = {"max_retries": 1, "interval_start": 0, "interval_max": 0.2}
# A wedged task must free its worker slot: nothing here runs longer than a few seconds (SMTP has
# its own 10 s timeout), so 60 s soft / 90 s hard is generous.
CELERY_TASK_SOFT_TIME_LIMIT = 60
CELERY_TASK_TIME_LIMIT = 90
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
# Paging must never queue behind a notification backlog, so escalations get their own queue.
CELERY_TASK_QUEUES = (Queue("escalations"), Queue("notifications"), Queue("default"))
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {
    "apps.escalations.tasks.*": {"queue": "escalations"},
    "apps.notifications.tasks.*": {"queue": "notifications"},
    "apps.core.tasks.*": {"queue": "default"},
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
    "purge-old-data": {
        "task": "apps.core.tasks.purge_old_data",
        "schedule": timedelta(hours=24),
    },
    "ops-heartbeat": {
        "task": "apps.core.tasks.heartbeat_task",
        "schedule": timedelta(seconds=60),
    },
    "sweep-stuck-notifications": {
        "task": "apps.notifications.tasks.sweep_stuck_notifications",
        # With STUCK_AFTER (90 s) this bounds how late a page can be when its delivery message
        # was lost (Redis down or wiped) to about 2.5 minutes.
        "schedule": timedelta(seconds=60),
    },
}


# --- Email -----------------------------------------------------------------
def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").lower() in {"1", "true", "yes", "on"}


EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
# Setting a host means "send real mail"; with none, pages are only printed to the log, which is
# right for local dev but means nobody is emailed. An explicit EMAIL_BACKEND always wins.
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend"
    if EMAIL_HOST
    else "django.core.mail.backends.console.EmailBackend",
)
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587" if _env_bool("EMAIL_USE_TLS") else "25"))
EMAIL_USE_TLS = _env_bool("EMAIL_USE_TLS")
EMAIL_USE_SSL = _env_bool("EMAIL_USE_SSL")
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
# Seconds. Without one, a blackholed SMTP host would pin a worker slot until the OS gave up.
EMAIL_TIMEOUT = int(os.environ.get("EMAIL_TIMEOUT", "10"))
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "pulse@localhost")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")

# --- Logging ---------------------------------------------------------------
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "apps.core.logging.RequestIDFilter"},
        "redact_request": {"()": "apps.core.logging.RedactRequestFilter"},
    },
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
            "filters": ["request_id", "redact_request"],
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
        "celery": {"level": "INFO"},
    },
}

# Delete resolved incidents (and their alerts, timeline, notifications) older than this many
# days. 0 = keep everything, which is the default. See docs/DATA_SAFETY.md.
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "0"))

# After rotating a service's integration key the old one keeps working this long.
INTEGRATION_KEY_GRACE_HOURS = int(os.environ.get("INTEGRATION_KEY_GRACE_HOURS", "24"))

# --- Content Security Policy -------------------------------------------------------------------
# For the pages Django itself renders (admin, one-tap action links, API docs). The SPA's policy is
# set by nginx (frontend/docker). CSP_MODE=report-only switches to reporting without enforcing,
# for trying a stricter policy against real traffic first.
from django.utils.csp import CSP  # noqa: E402

_CSP_POLICY = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF, CSP.NONCE],
    "style-src": [CSP.SELF, CSP.NONCE],
    "img-src": [CSP.SELF, "data:"],
    "font-src": [CSP.SELF],
    "connect-src": [CSP.SELF],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.NONE],
    "form-action": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
    "report-uri": "/api/v1/csp-report/",
}
CSP_MODE = os.environ.get("CSP_MODE", "enforce")
SECURE_CSP = _CSP_POLICY if CSP_MODE == "enforce" else {}
SECURE_CSP_REPORT_ONLY = _CSP_POLICY if CSP_MODE == "report-only" else {}
# The SPA's index page when Django serves it (the one-container demo image): the policy nginx sets
# for it everywhere else (frontend/docker/15-pulse-headers.envsh). Its scripts are plain files from
# 'self', so no nonce; React and Recharts set style attributes, hence inline styles only.
SPA_CSP = {
    **_CSP_POLICY,
    "script-src": [CSP.SELF],
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE],
    "connect-src": [CSP.SELF, *os.environ.get("CSP_CONNECT_EXTRA", "").split()],
}
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# --- Notification channels -----------------------------------------------------------------
# Everything is off until configured; an unconfigured channel fails its notifications
# immediately and visibly rather than retrying (docs/CHANNELS.md).
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")
TWILIO_API_BASE = os.environ.get("TWILIO_API_BASE", "https://api.twilio.com")
# The public origin Twilio and recipients reach us on. Twilio's request signature covers the exact
# URL it called, so this must match what is configured there, not an internal address.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL") or os.environ.get(
    "FRONTEND_URL", "http://localhost:5173"
)
# One-click acknowledge/resolve links in pages. Short-lived and single-use.
ACTION_LINK_TTL_HOURS = int(os.environ.get("ACTION_LINK_TTL_HOURS", "12"))
# Webhook destinations are user-supplied URLs, so private/loopback addresses are refused
# (SSRF). Only the test suite turns this on, to talk to a local fake receiver.
WEBHOOK_ALLOW_PRIVATE = False

# --- Observability ---------------------------------------------------------
# Everything here is off unless configured; see docs/OBSERVABILITY.md.
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
SENTRY_ENVIRONMENT = os.environ.get("SENTRY_ENVIRONMENT", "production")
SENTRY_RELEASE = os.environ.get("SENTRY_RELEASE") or os.environ.get("GIT_SHA") or None
SENTRY_TRACES_SAMPLE_RATE = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0"))
if SENTRY_DSN:
    from apps.core import sentry as _sentry

    _sentry.init(
        SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT,
        release=SENTRY_RELEASE,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
    )

# /metrics is disabled (404) unless a bearer token is configured. nginx does not proxy it, so
# it is reachable only on the internal network either way.
METRICS_TOKEN = os.environ.get("METRICS_TOKEN", "")
# Dead-man's switch: Beat -> worker -> GET this URL every minute. Silence means Pulse is down.
HEARTBEAT_URL = os.environ.get("HEARTBEAT_URL", "")
# Keep the JSON handler Django configured instead of Celery replacing it (worker logs stay JSON).
CELERY_WORKER_HIJACK_ROOT_LOGGER = False


# --- Demo mode ---------------------------------------------------------------------------------
# DEMO_MODE=1 runs Pulse as a single container for free hosting tiers: no Redis, no Celery. What a
# worker would do runs in-process right after commit; anything due later (escalation timers,
# delayed notification steps, retries, service-mode expiry) is driven by POST /internal/tick/,
# called by an external scheduler. Postgres already holds every timer and every pending page, so
# nothing is lost between ticks, only delayed. See docs/DEPLOY.md.
DEMO_MODE = env_bool("DEMO_MODE")
# Swagger UI at /api/docs/. It loads its script from a CDN onto the origin that holds the session
# cookie, so production serves it only when asked (API_DOCS=1); the schema stays at /api/schema/.
API_DOCS = env_bool("API_DOCS", True)
TASKS_INLINE = DEMO_MODE
# Shared @demo.local logins can't change their credentials or see other visitors' addresses
# (apps/core/demo.py). On with DEMO_MODE; set it alone for a full stack that seeds the demo logins.
DEMO_ACCOUNT_GUARD = env_bool("DEMO_ACCOUNT_GUARD", DEMO_MODE)
# The tick endpoint answers 404 unless DEMO_MODE is on and this is set.
TICK_SECRET = os.environ.get("TICK_SECRET", "")
# A public demo's logins are shared, so visitors can change anything they like: reseed it from
# scratch every this many hours, from the tick (0 = never).
DEMO_RESET_HOURS = int(os.environ.get("DEMO_RESET_HOURS", "0"))
# Also tick from within: after a response is sent, at most once per this many seconds (0 = never).
DEMO_SELF_TICK_SECONDS = int(os.environ.get("DEMO_SELF_TICK_SECONDS", "0"))
if DEMO_MODE:
    # Throttles, the sign-in lockout, idempotency keys and the heartbeat need one store that
    # every gunicorn worker shares; without Redis the database is it (`createcachetable`).
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "pulse_cache",
            # Django culls a third of the table at 300 rows (its default), alphabetically, which
            # would evict the daily-reset guard and the sign-in lockout counters (final audit).
            "OPTIONS": {"MAX_ENTRIES": 1_000_000},
        }
    }

# The built SPA. When set (the demo image), Django serves it: files through WhiteNoise, every
# client-side route through apps.core.spa. Elsewhere nginx serves it and this stays empty.
SPA_DIR = os.environ.get("SPA_DIR", "")
if SPA_DIR:
    WHITENOISE_ROOT = SPA_DIR
    # Vite fingerprints everything under /assets/, so those are cached for a year.
    WHITENOISE_IMMUTABLE_FILE_TEST = r"^/assets/.+-[\w-]{8,}\.\w+$"
