"""Glue between the database and the pure scoring service.

Reads grades and weights, calls ``scoring.services`` and stores the results in the
cached tables StudentLOScore / StudentPOScore.

Everything runs inside ``transaction.atomic`` with PostgreSQL's default READ COMMITTED
isolation. A reader never sees half-written data because the whole recompute commits at once.

Two transactions recomputing the *same* student (e.g. grades saved in two courses at the
same moment) are serialized by locking the student's row first (SELECT ... FOR UPDATE).
The second one waits, then reads the first one's committed grades, so no update is lost.
Locks are always taken in student-id order to avoid deadlocks.
"""

from collections import defaultdict

from django.contrib.auth import get_user_model
from django.db import transaction

from curriculum.models import AssessmentLOWeight, LearningOutcome, LOPOWeight
from grading.models import Enrollment, Grade
from scoring import services
from scoring.models import StudentLOScore, StudentPOScore


def _store(model, lookup, result):
    """Create/update the cached row, or delete it when there is no score."""
    if result is None:
        model.objects.filter(**lookup).delete()
        return
    model.objects.update_or_create(**lookup, defaults={"score": result.score, "is_incomplete": result.is_incomplete})


def _recompute_enrollment_los(enrollment):
    """Recompute LO scores for one enrollment. Returns {lo_id: ScoreResult}."""
    grades = {grade.assessment_id: grade.score for grade in Grade.objects.filter(enrollment=enrollment)}
    sources_by_lo = defaultdict(list)
    for link in AssessmentLOWeight.objects.filter(learning_outcome__offering=enrollment.offering_id):
        sources_by_lo[link.learning_outcome_id].append((link.assessment_id, link.weight))

    results = {}
    for lo in LearningOutcome.objects.filter(offering=enrollment.offering_id):
        result = services.compute_lo_score(sources_by_lo.get(lo.id, []), grades)
        _store(StudentLOScore, {"enrollment": enrollment, "learning_outcome": lo}, result)
        if result is not None:
            results[lo.id] = result
    return results


@transaction.atomic
def recompute_student(student):
    """Recompute every LO score and PO score of one student."""
    # Serialize concurrent recomputes of this student (no-op on SQLite).
    list(get_user_model().objects.select_for_update().filter(pk=student.pk))

    enrollments = list(Enrollment.objects.filter(student=student))
    lo_results = {}  # (enrollment_id, lo_id) -> ScoreResult
    enrollment_by_offering = {}
    for enrollment in enrollments:
        enrollment_by_offering[enrollment.offering_id] = enrollment
        for lo_id, result in _recompute_enrollment_los(enrollment).items():
            lo_results[(enrollment.id, lo_id)] = result

    sources_by_po = defaultdict(list)
    links = LOPOWeight.objects.filter(learning_outcome__offering__in=enrollment_by_offering.keys()).select_related(
        "learning_outcome"
    )
    for link in links:
        enrollment = enrollment_by_offering[link.learning_outcome.offering_id]
        sources_by_po[link.program_outcome_id].append(((enrollment.id, link.learning_outcome_id), link.weight))

    for po_id, sources in sources_by_po.items():
        result = services.compute_po_score(sources, lo_results)
        _store(StudentPOScore, {"student": student, "program_outcome_id": po_id}, result)

    # POs that lost all their sources (e.g. a link was deleted) must not keep a stale score.
    StudentPOScore.objects.filter(student=student).exclude(program_outcome_id__in=sources_by_po.keys()).delete()


@transaction.atomic
def recompute_offering(offering):
    """Recompute all students of an offering (used when weights change)."""
    for enrollment in Enrollment.objects.filter(offering=offering).select_related("student").order_by("student_id"):
        recompute_student(enrollment.student)
