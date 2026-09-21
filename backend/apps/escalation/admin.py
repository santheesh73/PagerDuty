from django.contrib import admin

from .models import EscalationLevel, EscalationPolicy


class EscalationLevelInline(admin.TabularInline):
    model = EscalationLevel
    extra = 1
    fields = ["order", "target_type", "target_user", "wait_minutes"]
    ordering = ["order"]


@admin.register(EscalationPolicy)
class EscalationPolicyAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "team", "is_active", "created_at"]
    list_filter = ["team", "is_active", "created_at"]
    search_fields = ["name", "slug", "team__name"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [EscalationLevelInline]


@admin.register(EscalationLevel)
class EscalationLevelAdmin(admin.ModelAdmin):
    list_display = ["policy", "order", "target_type", "target_user", "wait_minutes", "created_at"]
    list_filter = ["policy", "target_type"]
    search_fields = ["policy__name", "target_user__username"]
    ordering = ["policy", "order"]
