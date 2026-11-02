from django.conf import settings
from django.db import models

from curriculum.models import LearningOutcome, ProgramOutcome
from grading.models import Enrollment


class StudentLOScore(models.Model):
    """Cached (denormalized) learning outcome score; recomputed on grade/weight changes."""

    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="lo_scores")
    learning_outcome = models.ForeignKey(LearningOutcome, on_delete=models.CASCADE, related_name="student_scores")
    score = models.DecimalField(max_digits=7, decimal_places=4)
    is_incomplete = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["enrollment", "learning_outcome"], name="uniq_lo_score"),
        ]

    def __str__(self):
        return f"{self.enrollment.student} {self.learning_outcome.code}: {self.score}"


class StudentPOScore(models.Model):
    """Cached (denormalized) program outcome score across all of a student's courses."""

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="po_scores")
    program_outcome = models.ForeignKey(ProgramOutcome, on_delete=models.CASCADE, related_name="student_scores")
    score = models.DecimalField(max_digits=7, decimal_places=4)
    is_incomplete = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["student", "program_outcome"], name="uniq_po_score"),
        ]

    def __str__(self):
        return f"{self.student} PO{self.program_outcome.number}: {self.score}"
