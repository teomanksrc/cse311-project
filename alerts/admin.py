from django.contrib import admin

from alerts.models import POAlert


@admin.register(POAlert)
class POAlertAdmin(admin.ModelAdmin):
    list_display = ("student", "program_outcome", "score", "created_at", "emailed_at")
    list_filter = ("program_outcome",)
