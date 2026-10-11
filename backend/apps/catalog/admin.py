from django.contrib import admin

from .models import Service


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ["name", "team", "escalation_policy", "mode", "mode_until"]
    list_filter = ["mode", "team"]
    search_fields = ["name"]
    # Only a hash is stored; show the prefix so admins can tell keys apart.
    exclude = ["integration_key_hash", "previous_key_hash"]
    readonly_fields = ["integration_key_prefix", "previous_key_expires_at"]
