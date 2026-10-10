from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["idempotency_key", "user", "channel", "status", "attempts", "sent_at"]
    list_filter = ["status", "channel"]
    raw_id_fields = ["incident", "user"]
