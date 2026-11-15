from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import User
from accounts.permissions import role_required
from reporting.models import PerformanceReport
from reporting.services import build_report


def one_decimal(value):
    return None if value is None else f"{float(value):.1f}"


def report_rows(report):
    """PO rows for display, taken from the stored snapshot (numbers never come from the AI text)."""
    return [
        {
            "number": row["number"],
            "name": row["name"],
            "score": one_decimal(row["score"]),
            "incomplete": row["incomplete"],
            "average": one_decimal(row["department_average"]),
        }
        for row in report.scores_snapshot
    ]


def show_report(request, student):
    """Shared by the student page and the head page: POST builds a report, GET shows the latest one."""
    if request.method == "POST":
        build_report(student, created_by=request.user)
        return redirect(request.path)
    report = PerformanceReport.objects.filter(student=student).first()
    context = {
        "student": student,
        "report": report,
        "rows": report_rows(report) if report else [],
        "is_own": request.user == student,
    }
    return render(request, "reporting/report.html", context)


@role_required(User.Role.STUDENT)
def my_report(request):
    """Always the logged-in student's own report; there is no student id in the URL."""
    return show_report(request, request.user)


@role_required(User.Role.ADMIN, User.Role.HEAD)
def student_list(request):
    students = (
        User.objects.filter(role=User.Role.STUDENT)
        .annotate(last_report=Max("reports__created_at"))
        .order_by("last_name", "first_name", "username")
    )
    return render(request, "reporting/student_list.html", {"students": students})


@role_required(User.Role.ADMIN, User.Role.HEAD)
def student_report(request, student_id):
    student = get_object_or_404(User, id=student_id, role=User.Role.STUDENT)
    return show_report(request, student)
