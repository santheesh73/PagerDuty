"""Filters and relation fields that only know about the caller's own teams.

A filter or request field that validates against *every* team confirms which ids exist: another
team's id answered differently from an unknown one. Scoping the choices to the caller's teams makes
the two indistinguishable, in line with the 404-not-403 rule of docs/TENANCY.md.
"""

from typing import Any

from django.db.models import Model, QuerySet
from django_filters import ModelChoiceFilter
from rest_framework import serializers

from .views import scope_to_teams


def scoped_choice_filter(model: type[Model], team_lookup: str) -> ModelChoiceFilter:
    return ModelChoiceFilter(
        queryset=lambda request: scope_to_teams(
            model._default_manager.all(), request.user, team_lookup
        )
    )


class ScopedPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """A primary key that must belong to one of the caller's teams (staff: any)."""

    def __init__(self, *, team_lookup: str, **kwargs: Any) -> None:
        self.team_lookup = team_lookup
        super().__init__(**kwargs)

    def get_queryset(self) -> QuerySet[Any]:
        queryset = super().get_queryset()
        assert queryset is not None  # noqa: S101 (always given, see the serializers)
        request = self.context.get("request")
        if request is None:
            return queryset
        return scope_to_teams(queryset, request.user, self.team_lookup)
