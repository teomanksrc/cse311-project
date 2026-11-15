from django.conf import settings
from django.db import models


class PerformanceReport(models.Model):
    """A saved student performance report: rule-based summary plus optional AI commentary."""

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reports")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_reports"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    scores_snapshot = models.JSONField(help_text="PO rows the report was built from; scores are strings.")
    summary_text = models.TextField()
    ai_commentary = models.TextField(blank=True)
    ai_model = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Report for {self.student} ({self.created_at:%Y-%m-%d})"
