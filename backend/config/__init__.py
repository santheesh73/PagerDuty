"""Configuration package for Incident Management Platform."""
from .celery import app as celery_app

__all__ = ("celery_app",)
