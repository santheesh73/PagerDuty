from django.contrib import admin

from .models import Incident, IncidentEvent


class IncidentEventInline(admin.TabularInline):
    model = IncidentEvent
    extra = 0
    can_delete = False
    readonly_fields = ["type", "actor", "message", "data", "created_at"]


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ["number", "title", "service", "status", "urgency", "assignee", "triggered_at"]
    list_filter = ["status", "urgency", "service"]
    search_fields = ["title", "dedup_key"]
    readonly_fields = ["number", "escalation_snapshot"]
    inlines = [IncidentEventInline]
