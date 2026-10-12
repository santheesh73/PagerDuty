"""Swagger UI is served from a pinned release, never @latest."""

import re

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


def test_the_docs_page_pins_the_swagger_ui_release() -> None:
    page = Client().get("/api/docs/")
    assert page.status_code == 200
    scripts = re.findall(r'src="(https://cdn\.jsdelivr\.net[^"]+)"', page.content.decode())
    assert scripts, "the page loads Swagger UI from the CDN"
    assert all(re.search(r"swagger-ui-dist@\d+\.\d+\.\d+/", s) for s in scripts), scripts
    assert not any("@latest" in s for s in scripts)
