from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    """Read-only: the table is append-only in the database itself."""

    list_display = [
        "created_at",
        "action",
        "actor_email",
        "team_id",
        "target_type",
        "target_id",
        "ip",
    ]
    list_filter = ["action"]
    search_fields = ["actor_email", "action", "target_id"]
    readonly_fields = [f.name for f in AuditEvent._meta.fields]

    def has_add_permission(self, request: object) -> bool:
        return False

    def has_change_permission(self, request: object, obj: object = None) -> bool:
        return False

    def has_delete_permission(self, request: object, obj: object = None) -> bool:
        return False
