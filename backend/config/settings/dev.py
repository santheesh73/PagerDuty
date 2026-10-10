from .base import *  # noqa: F403

DEBUG = True
SECRET_KEY = SECRET_KEY or "dev-only-insecure-key-do-not-use-in-production"  # noqa: F405
ALLOWED_HOSTS = ["*"]
