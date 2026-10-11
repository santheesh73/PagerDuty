"""Query-string parsing for list filters, in one place.

A malformed filter is the caller's mistake, so it is a 422 naming the parameter. Never a 500 (the
ORM choking on `team=abc`), and never silently ignored (a dashboard asking for `status=triggred`
would otherwise be shown every incident, or none, and look correct).
"""

from datetime import UTC, datetime

from django.http import QueryDict
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError


def int_param(params: QueryDict, name: str) -> int | None:
    raw = params.get(name)
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except ValueError:
        raise ValidationError({name: "Expected an integer."}) from None


def datetime_param(params: QueryDict, name: str) -> datetime | None:
    """An ISO-8601 instant; a naive one is read as UTC."""
    raw = params.get(name)
    if not raw:
        return None
    value = parse_datetime(raw)
    if value is None:
        raise ValidationError({name: "Expected an ISO-8601 datetime."})
    return value if timezone.is_aware(value) else timezone.make_aware(value, UTC)


def choices_param(params: QueryDict, name: str, allowed: set[str]) -> list[str] | None:
    """A comma-separated subset of `allowed`."""
    values = [v for v in params.get(name, "").split(",") if v]
    if not values:
        return None
    if unknown := sorted(set(values) - allowed):
        raise ValidationError(
            {name: f"Unknown value(s) {', '.join(unknown)}; expected {', '.join(sorted(allowed))}."}
        )
    return values
