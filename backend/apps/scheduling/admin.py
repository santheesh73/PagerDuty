from django.contrib import admin

from .models import Schedule, ScheduleRotation


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "team", "timezone", "is_primary", "is_active"]
    list_filter = ["team", "is_active", "is_primary"]
    search_fields = ["name", "slug"]
    ordering = ["name"]


@admin.register(ScheduleRotation)
class ScheduleRotationAdmin(admin.ModelAdmin):
    list_display = ["schedule", "user", "start_time", "end_time", "is_override"]
    list_filter = ["schedule", "is_override", "user"]
    search_fields = ["user__username", "schedule__name"]
    ordering = ["start_time", "id"]
