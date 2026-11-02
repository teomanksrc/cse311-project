from django.db.models import Avg, Count, Q
from django.shortcuts import render

from accounts.models import User
from accounts.permissions import role_required
from curriculum.models import ProgramOutcome
from grading.models import Enrollment
from scoring.models import StudentLOScore, StudentPOScore


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
    stats = ProgramOutcome.objects.annotate(
        average=Avg("student_scores__score"),
        students=Count("student_scores"),
        incomplete=Count("student_scores", filter=Q(student_scores__is_incomplete=True)),
    ).order_by("number")
    rows = [
        {"po": po, "average": to_float(po.average), "students": po.students, "incomplete": po.incomplete}
        for po in stats
    ]
    chart = {"labels": [f"PO{r['po'].number}" for r in rows], "scores": [r["average"] for r in rows]}
    return render(request, "scoring/department_dashboard.html", {"rows": rows, "chart": chart})
