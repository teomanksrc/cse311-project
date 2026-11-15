from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from accounts.models import User
from accounts.permissions import role_required
from curriculum.models import ProgramOutcome
from grading.models import Enrollment
from scoring.models import DepartmentPOStat, StudentLOScore, StudentPOScore
from scoring.stats import refresh_department_stats


def to_float(value):
    return None if value is None else round(float(value), 1)


@role_required(User.Role.STUDENT)
def student_dashboard(request):
    """Shows only the logged-in student's own data; there is no student id in the URL."""
    scores = {s.program_outcome_id: s for s in StudentPOScore.objects.filter(student=request.user)}
    profile = []
    for po in ProgramOutcome.objects.all():
        score = scores.get(po.id)
        profile.append(
            {
                "po": po,
                "score": to_float(score.score) if score else None,
                "incomplete": bool(score and score.is_incomplete),
            }
        )

    courses = []
    enrollments = Enrollment.objects.filter(student=request.user).select_related("offering__course")
    for enrollment in enrollments:
        lo_scores = StudentLOScore.objects.filter(enrollment=enrollment).select_related("learning_outcome")
        courses.append(
            {
                "offering": enrollment.offering,
                "grades": enrollment.grades.select_related("assessment").order_by("assessment__name"),
                "lo_scores": [
                    {"lo": s.learning_outcome, "score": to_float(s.score), "incomplete": s.is_incomplete}
                    for s in lo_scores
                ],
            }
        )

    chart = {
        "labels": [f"PO{row['po'].number}" for row in profile],
        "scores": [row["score"] for row in profile],
    }
    return render(request, "scoring/student_dashboard.html", {"profile": profile, "courses": courses, "chart": chart})


@role_required(User.Role.ADMIN, User.Role.HEAD)
def department_dashboard(request):
    # Reads the (materialized) view; see scoring/stats.py for when it is refreshed.
    stats = DepartmentPOStat.objects.select_related("program_outcome").order_by("program_outcome__number")
    rows = [
        {"po": s.program_outcome, "average": to_float(s.average), "students": s.students, "incomplete": s.incomplete}
        for s in stats
    ]
    chart = {"labels": [f"PO{r['po'].number}" for r in rows], "scores": [r["average"] for r in rows]}
    return render(request, "scoring/department_dashboard.html", {"rows": rows, "chart": chart})


@require_POST
@role_required(User.Role.ADMIN, User.Role.HEAD)
def refresh_department(request):
    """For changes made in the Django admin site, which do not pass through the grade-entry views."""
    refresh_department_stats()
    messages.success(request, "Department statistics refreshed.")
    return redirect("scoring:department_dashboard")
