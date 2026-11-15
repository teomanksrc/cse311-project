"""Low-score alerts: keep POAlert rows in step with StudentPOScore, then e-mail the new ones.

E-mail is never sent from signals or from the score recompute. Those run inside the
grade-saving transaction and hold row locks; a slow or failing mail server must never
block or roll back grade entry. Alerts are synced and sent separately (command or button).
"""

from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from alerts.models import POAlert
from reporting.rules import LOW_SCORE_THRESHOLD
from scoring.models import StudentPOScore


def sync_alerts():
    """Create, update and delete alerts so they match the scores. Returns the counts."""
    counts = {"created": 0, "updated": 0, "deleted": 0}
    with transaction.atomic():
        low_scores = {
            (s.student_id, s.program_outcome_id): s.score
            for s in StudentPOScore.objects.filter(score__lt=LOW_SCORE_THRESHOLD)
        }
        for alert in POAlert.objects.all():
            score = low_scores.pop((alert.student_id, alert.program_outcome_id), None)  # what is left needs a new alert
            if score is None:  # recovered, or the score row is gone
                alert.delete()
                counts["deleted"] += 1
            elif alert.score != score:
                alert.score = score
                alert.save()
                counts["updated"] += 1
        for (student_id, po_id), score in low_scores.items():
            POAlert.objects.create(student_id=student_id, program_outcome_id=po_id, score=score)
            counts["created"] += 1
    return counts


def send_pending_alerts():
    """One e-mail per student with un-mailed alerts. Returns the counts."""
    counts = {"sent": 0, "skipped": 0, "failed": 0}
    pending = POAlert.objects.filter(emailed_at__isnull=True).select_related("student", "program_outcome")
    by_student = {}
    for alert in pending.order_by("student_id", "program_outcome__number"):
        by_student.setdefault(alert.student, []).append(alert)

    for student, alerts in by_student.items():
        if not student.email:
            counts["skipped"] += 1  # stays pending
            continue
        lines = [f"- PO{a.program_outcome.number} ({a.program_outcome.short_name}): {a.score:.1f}" for a in alerts]
        body = (
            f"Hello {student.get_full_name() or student.username},\n\n"
            f"These program outcomes are below {LOW_SCORE_THRESHOLD}:\n\n" + "\n".join(lines) + "\n\n"
            f"See your report in the PO system: {reverse('reporting:my_report')}\n"
        )
        try:
            send_mail("Low program outcome score alert", body, None, [student.email])
        except OSError:  # includes smtplib.SMTPException; try again on the next run
            counts["failed"] += 1
            continue
        with transaction.atomic():
            POAlert.objects.filter(id__in=[a.id for a in alerts]).update(emailed_at=timezone.now())
        counts["sent"] += 1
    return counts
