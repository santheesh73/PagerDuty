from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin

from .models import Team, TeamMembership, User


@admin.register(User)
class UserAdmin(DefaultUserAdmin):
    list_display = ["username", "email", "first_name", "last_name", "is_active", "is_staff"]
    search_fields = ["username", "email", "first_name", "last_name"]
    list_filter = ["is_active", "is_staff"]


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_active", "created_at"]
    search_fields = ["name", "slug", "description"]
    list_filter = ["is_active"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(TeamMembership)
class TeamMembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "team", "role", "is_active", "joined_at"]
    list_filter = ["role", "is_active", "team"]
    search_fields = ["user__username", "user__email", "team__name"]
    autocomplete_fields = ["user", "team"]
