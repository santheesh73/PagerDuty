from django.contrib import admin

from .models import Service


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ["name", "team", "escalation_policy", "mode", "mode_until"]
    list_filter = ["mode", "team"]
    search_fields = ["name"]
    # Never render the integration key in list views or change forms.
    exclude = ["integration_key"]
