from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "incident",
        "recipient",
        "channel",
        "status",
        "attempt_count",
        "sent_at",
        "created_at",
    ]
    list_filter = ["channel", "status", "created_at"]
    search_fields = ["recipient__username", "recipient__email", "incident__title", "dedupe_key"]
    readonly_fields = [
        "incident",
        "recipient",
        "channel",
        "escalation_level",
        "dedupe_key",
        "attempt_count",
        "sent_at",
        "failed_at",
        "last_error",
        "created_at",
        "updated_at",
    ]

    def has_add_permission(self, request):
        return False
