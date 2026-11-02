from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import User
from accounts.permissions import role_required
from curriculum.models import Assessment, CourseOffering
from grading.models import Enrollment, Grade


@role_required(User.Role.INSTRUCTOR)
def instructor_home(request):
    offerings = (
        CourseOffering.objects.filter(instructor=request.user).select_related("course").prefetch_related("assessments")
    )
    return render(request, "grading/instructor_home.html", {"offerings": offerings})


def parse_score(raw):
    """Return (score, error). Blank means 'no grade'."""
    raw = raw.strip()
    if raw == "":
        return None, None
    try:
        score = Decimal(raw)
    except InvalidOperation:
        return None, "Not a number"
    if not Decimal("0") <= score <= Decimal("100"):
        return None, "Must be between 0 and 100"
    return score, None


@role_required(User.Role.INSTRUCTOR)
def enter_grades(request, assessment_id):
    # Only the instructor of the offering may see or edit its grades (others get 404).
    assessment = get_object_or_404(
        Assessment.objects.select_related("offering__course"),
        pk=assessment_id,
        offering__instructor=request.user,
    )
    enrollments = list(
        Enrollment.objects.filter(offering=assessment.offering).select_related("student").order_by("student__last_name")
    )
    existing = {g.enrollment_id: g for g in Grade.objects.filter(assessment=assessment)}

    rows = []
    for enrollment in enrollments:
        grade = existing.get(enrollment.id)
        rows.append({"enrollment": enrollment, "value": grade.score if grade else "", "error": None})

    if request.method == "POST":
        parsed = {}
        has_error = False
        for row in rows:
            raw = request.POST.get(f"score_{row['enrollment'].id}", "")
            row["value"] = raw
            score, error = parse_score(raw)
            row["error"] = error
            has_error = has_error or error is not None
            parsed[row["enrollment"].id] = score

        if not has_error:
            # Grade writes and the score recomputation (via signals) commit together or not at all.
            # Save in student-id order: recomputes lock students in the same order, which avoids deadlocks.
            student_of = {row["enrollment"].id: row["enrollment"].student_id for row in rows}
            with transaction.atomic():
                for enrollment_id, score in sorted(parsed.items(), key=lambda item: student_of[item[0]]):
                    if score is None:
                        Grade.objects.filter(enrollment_id=enrollment_id, assessment=assessment).delete()
                    else:
                        Grade.objects.update_or_create(
                            enrollment_id=enrollment_id, assessment=assessment, defaults={"score": score}
                        )
            messages.success(request, "Grades saved and scores recalculated.")
            return redirect("grading:enter_grades", assessment_id=assessment.id)
        messages.error(request, "Nothing was saved. Please fix the highlighted grades.")

    return render(request, "grading/enter_grades.html", {"assessment": assessment, "rows": rows})
