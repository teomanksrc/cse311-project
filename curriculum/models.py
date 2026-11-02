from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class ProgramOutcome(models.Model):
    """One of the department's 11 Program Outcomes (department-wide)."""

    number = models.PositiveSmallIntegerField(unique=True)
    short_name = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return f"PO{self.number}"


class Course(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class CourseOffering(models.Model):
    """A course taught in a given term. LOs, assessments and weights live here."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="offerings")
    term = models.CharField(max_length=20, help_text='e.g. "2026-Fall"')
    instructor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="taught_offerings")

    class Meta:
        ordering = ["-term", "course__code"]
        constraints = [
            models.UniqueConstraint(fields=["course", "term"], name="uniq_offering_course_term"),
        ]

    def __str__(self):
        return f"{self.course.code} ({self.term})"


class LearningOutcome(models.Model):
    offering = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name="learning_outcomes")
    code = models.CharField(max_length=20)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["offering", "code"]
        constraints = [
            models.UniqueConstraint(fields=["offering", "code"], name="uniq_lo_offering_code"),
        ]

    def __str__(self):
        return f"{self.offering.course.code} {self.code}"


class Assessment(models.Model):
    offering = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name="assessments")
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["offering", "name"]
        constraints = [
            models.UniqueConstraint(fields=["offering", "name"], name="uniq_assessment_offering_name"),
        ]

    def __str__(self):
        return f"{self.offering.course.code} {self.name}"


class AssessmentLOWeight(models.Model):
    """How much an assessment counts towards a learning outcome (any positive decimal)."""

    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="lo_weights")
    learning_outcome = models.ForeignKey(LearningOutcome, on_delete=models.CASCADE, related_name="assessment_weights")
    weight = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["assessment", "learning_outcome"], name="uniq_assessment_lo"),
            models.CheckConstraint(condition=models.Q(weight__gt=0), name="assessment_lo_weight_positive"),
        ]

    def clean(self):
        if self.assessment_id and self.learning_outcome_id:
            if self.assessment.offering_id != self.learning_outcome.offering_id:
                raise ValidationError("Assessment and learning outcome must belong to the same course offering.")
        if self.weight is not None and self.weight <= Decimal("0"):
            raise ValidationError({"weight": "Weight must be greater than 0."})

    def __str__(self):
        return f"{self.assessment.name} -> {self.learning_outcome.code} ({self.weight})"


class LOPOWeight(models.Model):
    """How strongly a learning outcome contributes to a program outcome (integer 1-5)."""

    learning_outcome = models.ForeignKey(LearningOutcome, on_delete=models.CASCADE, related_name="po_weights")
    program_outcome = models.ForeignKey(ProgramOutcome, on_delete=models.CASCADE, related_name="lo_weights")
    weight = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["learning_outcome", "program_outcome"], name="uniq_lo_po"),
            models.CheckConstraint(condition=models.Q(weight__gte=1, weight__lte=5), name="lo_po_weight_1_to_5"),
        ]

    def clean(self):
        if self.weight is not None and not 1 <= self.weight <= 5:
            raise ValidationError({"weight": "Weight must be between 1 and 5."})

    def __str__(self):
        return f"{self.learning_outcome.code} -> PO{self.program_outcome.number} ({self.weight})"
