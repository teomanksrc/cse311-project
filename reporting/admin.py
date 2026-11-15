from django.contrib import admin

from reporting.models import PerformanceReport


@admin.register(PerformanceReport)
class PerformanceReportAdmin(admin.ModelAdmin):
    list_display = ("student", "created_by", "created_at", "ai_model")
    readonly_fields = ("created_at",)
