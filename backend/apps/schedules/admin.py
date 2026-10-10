from django.contrib import admin

from .models import LayerMember, Schedule, ScheduleLayer, ScheduleOverride


class ScheduleLayerInline(admin.StackedInline):
    model = ScheduleLayer
    extra = 0


class ScheduleOverrideInline(admin.TabularInline):
    model = ScheduleOverride
    extra = 0


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ["name", "team", "timezone"]
    inlines = [ScheduleLayerInline, ScheduleOverrideInline]


@admin.register(LayerMember)
class LayerMemberAdmin(admin.ModelAdmin):
    list_display = ["layer", "position", "user"]
