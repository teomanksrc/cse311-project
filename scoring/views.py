from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from accounts.models import User
from accounts.permissions import role_required
from curriculum.models import CourseOffering, ProgramOutcome
from grading.models import Enrollment, Grade
from reporting.rules import LOW_SCORE_THRESHOLD
from scoring.models import DepartmentPOStat, StudentLOScore, StudentPOScore
from scoring.stats import refresh_department_stats

# PO coverage thresholds: fewer contributing offerings than WEAK_BELOW_OFFERINGS is "Weak".
WEAK_BELOW_OFFERINGS = 2


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

    # Compare the full-precision score; the rounded one is for display only.
    low_scores = [row for row in profile if row["po"].id in scores and scores[row["po"].id].score < LOW_SCORE_THRESHOLD]

    courses = []
    enrollments = (
        Enrollment.objects.filter(student=request.user)
        .select_related("offering__course")
        .prefetch_related("offering__assessments")
    )
    # One query for all of this student's grades: {(enrollment id, assessment id): score}
    grade_scores = {
        (g.enrollment_id, g.assessment_id): g.score for g in Grade.objects.filter(enrollment__student=request.user)
    }
    for enrollment in enrollments:
        lo_scores = StudentLOScore.objects.filter(enrollment=enrollment).select_related("learning_outcome")
        # Every assessment of the offering; score is None when it has not been graded.
        grades = [
            {"assessment": a, "score": grade_scores.get((enrollment.id, a.id))}
            for a in enrollment.offering.assessments.all()
        ]
        courses.append(
            {
                "offering": enrollment.offering,
                "grades": grades,
                "has_ng": any(g["score"] is None for g in grades),
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
    return render(
        request,
        "scoring/student_dashboard.html",
        {
            "profile": profile,
            "courses": courses,
            "chart": chart,
            "low_scores": low_scores,
            "threshold": LOW_SCORE_THRESHOLD,
        },
    )


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


@role_required(User.Role.ADMIN, User.Role.HEAD)
def po_coverage(request):
    """Which POs are weakly covered by the syllabi? One annotated query for all POs."""
    terms = list(CourseOffering.objects.order_by("-term").values_list("term", flat=True).distinct())
    term = request.GET.get("term", "")
    if term not in terms:
        term = ""
    in_term = Q(lo_weights__learning_outcome__offering__term=term) if term else Q()
    pos = ProgramOutcome.objects.annotate(
        offerings=Count("lo_weights__learning_outcome__offering", filter=in_term, distinct=True),
        los=Count("lo_weights__learning_outcome", filter=in_term, distinct=True),
        weight_sum=Coalesce(Sum("lo_weights__weight", filter=in_term), 0),
    ).order_by("number")
    rows = []
    for po in pos:
        if po.los == 0:
            status = "Not covered"
        elif po.offerings < WEAK_BELOW_OFFERINGS:
            status = "Weak"
        else:
            status = "Covered"
        rows.append({"po": po, "offerings": po.offerings, "los": po.los, "weight_sum": po.weight_sum, "status": status})
    return render(request, "scoring/po_coverage.html", {"rows": rows, "terms": terms, "term": term})
