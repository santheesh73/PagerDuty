from django.contrib import admin

from .models import Service


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "team", "status", "is_active", "created_at"]
    list_filter = ["status", "team", "is_active"]
    search_fields = ["name", "slug", "description"]
    prepopulated_fields = {"slug": ("name",)}
