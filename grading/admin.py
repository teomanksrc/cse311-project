from django.contrib import admin

from grading.models import Enrollment, Grade


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "offering")
    list_filter = ("offering",)
    search_fields = ("student__username", "student__first_name", "student__last_name")


@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "assessment", "score")
    list_filter = ("assessment__offering", "assessment")
