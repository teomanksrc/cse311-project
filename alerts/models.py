from django.conf import settings
from django.db import models

from curriculum.models import ProgramOutcome


class POAlert(models.Model):
    """A student's PO score is below the threshold. One row per student and PO.

    ``emailed_at`` is empty until the e-mail about this alert has been handed to the mail backend,
    so nobody is mailed twice about the same thing.
    """

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="po_alerts")
    program_outcome = models.ForeignKey(ProgramOutcome, on_delete=models.CASCADE, related_name="alerts")
    score = models.DecimalField(max_digits=7, decimal_places=4)  # the score when the alert was last synced
    created_at = models.DateTimeField(auto_now_add=True)
    emailed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["student", "program_outcome"], name="uniq_po_alert"),
        ]

    def __str__(self):
        return f"{self.student} PO{self.program_outcome.number}: {self.score}"
