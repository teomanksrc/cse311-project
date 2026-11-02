from django.contrib import admin

from curriculum.models import (
    Assessment,
    AssessmentLOWeight,
    Course,
    CourseOffering,
    LearningOutcome,
    LOPOWeight,
    ProgramOutcome,
)


@admin.register(ProgramOutcome)
class ProgramOutcomeAdmin(admin.ModelAdmin):
    list_display = ("number", "short_name")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


@admin.register(CourseOffering)
class CourseOfferingAdmin(admin.ModelAdmin):
    list_display = ("course", "term", "instructor")
    list_filter = ("term", "course")


@admin.register(LearningOutcome)
class LearningOutcomeAdmin(admin.ModelAdmin):
    list_display = ("code", "offering", "description")
    list_filter = ("offering",)


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ("name", "offering")
    list_filter = ("offering",)


@admin.register(AssessmentLOWeight)
class AssessmentLOWeightAdmin(admin.ModelAdmin):
    list_display = ("assessment", "learning_outcome", "weight")
    list_filter = ("assessment__offering",)


@admin.register(LOPOWeight)
class LOPOWeightAdmin(admin.ModelAdmin):
    list_display = ("learning_outcome", "program_outcome", "weight")
    list_filter = ("program_outcome", "learning_outcome__offering")
