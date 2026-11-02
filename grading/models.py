from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from curriculum.models import Assessment, CourseOffering


class Enrollment(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enrollments")
    offering = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name="enrollments")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["student", "offering"], name="uniq_enrollment_student_offering"),
        ]

    def __str__(self):
        return f"{self.student} in {self.offering}"


class Grade(models.Model):
    """A student's score (0-100) on one assessment."""

    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="grades")
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="grades")
    score = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["enrollment", "assessment"], name="uniq_grade_enrollment_assessment"),
            models.CheckConstraint(condition=models.Q(score__gte=0, score__lte=100), name="grade_score_0_to_100"),
        ]
        # No extra indexes: Django already indexes both foreign keys.

    def clean(self):
        if self.score is not None and not Decimal("0") <= self.score <= Decimal("100"):
            raise ValidationError({"score": "Score must be between 0 and 100."})
        if self.enrollment_id and self.assessment_id:
            if self.enrollment.offering_id != self.assessment.offering_id:
                raise ValidationError("Assessment must belong to the enrolled course offering.")

    def __str__(self):
        return f"{self.enrollment.student} {self.assessment.name}: {self.score}"
