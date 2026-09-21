from django.contrib import admin

from .models import Incident, IncidentEvent


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "title",
        "service",
        "severity",
        "status",
        "assigned_user",
        "triggered_at",
        "acknowledged_at",
        "resolved_at",
    ]
    list_filter = ["status", "severity", "service"]
    search_fields = ["title", "fingerprint"]
    readonly_fields = ["fingerprint", "created_at", "updated_at"]

    def has_delete_permission(self, request, obj=None):
        # Prevent deletion of operational incidents with historical event traces
        if obj and obj.events.exists():
            return False
        return super().has_delete_permission(request, obj)


@admin.register(IncidentEvent)
class IncidentEventAdmin(admin.ModelAdmin):
    list_display = ["id", "incident", "event_type", "actor", "created_at"]
    list_filter = ["event_type", "created_at"]
    search_fields = ["incident__title", "incident__fingerprint"]
    readonly_fields = [
        "incident",
        "event_type",
        "actor",
        "metadata",
        "created_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
