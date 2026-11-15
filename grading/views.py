from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from openpyxl import Workbook

from accounts.models import User
from accounts.permissions import role_required
from curriculum.models import Assessment, CourseOffering
from grading.imports import MAX_FILE_SIZE, parse_score, read_rows, validate_import
from grading.models import Enrollment, Grade
from scoring.stats import refresh_department_stats


@role_required(User.Role.INSTRUCTOR)
def instructor_home(request):
    offerings = (
        CourseOffering.objects.filter(instructor=request.user).select_related("course").prefetch_related("assessments")
    )
    return render(request, "grading/instructor_home.html", {"offerings": offerings})


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
            refresh_department_stats()  # after the commit
            messages.success(request, "Grades saved and scores recalculated.")
            return redirect("grading:enter_grades", assessment_id=assessment.id)
        messages.error(request, "Nothing was saved. Please fix the highlighted grades.")

    return render(request, "grading/enter_grades.html", {"assessment": assessment, "rows": rows})


def get_own_offering(request, offering_id):
    return get_object_or_404(CourseOffering.objects.select_related("course"), pk=offering_id, instructor=request.user)


def enrolled_students(offering):
    """Enrollments of the offering that have a student number, ordered by student number."""
    return (
        Enrollment.objects.filter(offering=offering, student__student_number__isnull=False)
        .select_related("student")
        .order_by("student__student_number")
    )


@role_required(User.Role.INSTRUCTOR)
def import_template(request, offering_id):
    """Excel file with the header row and one line per enrolled student.

    It is .xlsx and not .csv on purpose: Excel with Turkish regional settings puts a
    comma-separated file into a single column, so the instructor cannot fill it in.
    """
    offering = get_own_offering(request, offering_id)
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["student_number"] + [a.name for a in offering.assessments.all()])
    for enrollment in enrolled_students(offering):
        sheet.append([enrollment.student.student_number])  # kept as text, so leading zeros survive
    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="grades_{offering.course.code}.xlsx"'
    workbook.save(response)
    return response


@role_required(User.Role.INSTRUCTOR)
def import_grades(request, offering_id):
    offering = get_own_offering(request, offering_id)
    errors = []
    if request.method == "POST":
        upload = request.FILES.get("file")
        if upload is None:
            errors = ["Choose a file first."]
        elif upload.size > MAX_FILE_SIZE:
            errors = ["The file is too large (limit is 1 MB)."]
        else:
            rows, error = read_rows(upload.name, upload.read())
            if error:
                errors = [error]
            else:
                assessment_ids = {a.name: a.id for a in offering.assessments.all()}
                enrollments = {e.student.student_number: (e.id, e.student_id) for e in enrolled_students(offering)}
                grades, errors = validate_import(rows, assessment_ids, enrollments)

        if not errors:
            # Same rule as enter_grades: write in student-id order, all in one transaction.
            grades.sort(key=lambda g: (g["student_id"], g["assessment_id"]))
            existing = {
                (g.enrollment_id, g.assessment_id): g.score for g in Grade.objects.filter(assessment__offering=offering)
            }
            created = updated = 0
            with transaction.atomic():
                for g in grades:
                    old_score = existing.get((g["enrollment_id"], g["assessment_id"]))
                    if old_score == g["score"]:
                        continue  # unchanged: no write, no recompute
                    Grade.objects.update_or_create(
                        enrollment_id=g["enrollment_id"],
                        assessment_id=g["assessment_id"],
                        defaults={"score": g["score"]},
                    )
                    if old_score is None:
                        created += 1
                    else:
                        updated += 1
            refresh_department_stats()  # after the commit
            messages.success(request, f"Import finished: {created} grade(s) created, {updated} updated.")
            return redirect("grading:import_grades", offering_id=offering.id)
        messages.error(request, "Nothing was imported. Please fix the errors below.")

    return render(
        request,
        "grading/import_grades.html",
        {"offering": offering, "errors": errors, "assessments": offering.assessments.all()},
    )
