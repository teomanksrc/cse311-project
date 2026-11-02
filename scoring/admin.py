from django.contrib import admin

from scoring.models import StudentLOScore, StudentPOScore


@admin.register(StudentLOScore)
class StudentLOScoreAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "learning_outcome", "score", "is_incomplete")
    list_filter = ("is_incomplete", "learning_outcome__offering")


@admin.register(StudentPOScore)
class StudentPOScoreAdmin(admin.ModelAdmin):
    list_display = ("student", "program_outcome", "score", "is_incomplete")
    list_filter = ("is_incomplete", "program_outcome")
