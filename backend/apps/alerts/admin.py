from django.contrib import admin

from .models import Alert


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ["id", "service", "incident", "severity", "source", "fingerprint", "received_at"]
    list_filter = ["severity", "source", "service"]
    search_fields = ["message", "fingerprint"]
    readonly_fields = ["incident", "fingerprint", "received_at", "created_at"]
