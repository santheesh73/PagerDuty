from django.contrib import admin

from .models import EscalationPolicy, EscalationRule, EscalationTarget


class EscalationRuleInline(admin.TabularInline):
    model = EscalationRule
    extra = 0


@admin.register(EscalationPolicy)
class EscalationPolicyAdmin(admin.ModelAdmin):
    list_display = ["name", "team", "num_loops"]
    list_filter = ["team"]
    inlines = [EscalationRuleInline]


@admin.register(EscalationTarget)
class EscalationTargetAdmin(admin.ModelAdmin):
    list_display = ["rule", "position", "target_user", "target_schedule"]
