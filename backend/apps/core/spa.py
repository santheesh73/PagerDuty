"""The SPA's index page, for every client-side route, when Django serves the SPA (SPA_DIR set).

That is only the one-container demo image; everywhere else nginx serves the SPA and this view
answers 404 like any unknown path. The page gets the SPA's own policy (scripts from 'self', no
nonce) rather than the nonce policy Django uses for its own pages.
"""

from collections.abc import Callable, Collection, Mapping
from functools import cache
from pathlib import Path
from typing import cast

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csp import csp_override, csp_report_only_override
from django.views.decorators.http import require_safe


@cache
def _index(spa_dir: str) -> bytes:
    return (Path(spa_dir) / "index.html").read_bytes()


View = Callable[[HttpRequest], HttpResponse]


def _with_spa_policy(view: View) -> View:
    policy = cast(Mapping[str, Collection[str] | str], settings.SPA_CSP)
    if settings.CSP_MODE == "report-only":
        return csp_report_only_override(policy)(view)
    return csp_override(policy)(view)


@never_cache  # a new deploy's index must win over a stale one
@require_safe
def _index_view(request: HttpRequest) -> HttpResponse:
    if not settings.SPA_DIR:
        raise Http404
    try:
        body = _index(settings.SPA_DIR)
    except FileNotFoundError:
        raise Http404 from None
    return HttpResponse(body, content_type="text/html; charset=utf-8")


def index(request: HttpRequest) -> HttpResponse:
    return _with_spa_policy(_index_view)(request)
