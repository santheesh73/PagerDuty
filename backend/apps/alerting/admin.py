from django.contrib import admin

from .models import Alert


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ["summary", "service", "severity", "status", "dedup_key", "received_at"]
    list_filter = ["severity", "status"]
    search_fields = ["summary", "dedup_key"]
    raw_id_fields = ["incident"]
