from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import User
from accounts.permissions import role_required
from curriculum.forms import AssessmentForm, LearningOutcomeForm
from curriculum.models import (
    Assessment,
    AssessmentLOWeight,
    CourseOffering,
    LearningOutcome,
    LOPOWeight,
    ProgramOutcome,
)
from grading.models import Grade
from scoring.models import StudentLOScore
from scoring.stats import refresh_department_stats


def get_own_offering(request, offering_id):
    """Only the instructor of the offering may configure it (others get 404)."""
    return get_object_or_404(CourseOffering.objects.select_related("course"), pk=offering_id, instructor=request.user)


def parse_assessment_weight(raw):
    """Return (weight, error). Blank means 'no link'. Any positive decimal that fits the column."""
    raw = raw.strip()
    if raw == "":
        return None, None
    try:
        weight = Decimal(raw)
    except InvalidOperation:
        return None, "Not a number"
    if not weight.is_finite() or weight <= 0:
        return None, "Must be greater than 0"
    if weight.as_tuple().exponent < -2:
        return None, "At most 2 decimal places"
    if weight >= 10000:
        return None, "Too large"
    return weight, None


def parse_po_weight(raw):
    """Return (weight, error). Blank means 'no link'. Integer 1-5."""
    raw = raw.strip()
    if raw == "":
        return None, None
    try:
        weight = int(raw)
    except ValueError:
        return None, "Whole number 1-5"
    if not 1 <= weight <= 5:
        return None, "Must be 1-5"
    return weight, None


def build_setup_context(offering, assessment_values=None, assessment_errors=None, po_values=None, po_errors=None):
    """Context for the setup page. The *_values / *_errors dicts hold a rejected POST, keyed by input name."""
    los = list(offering.learning_outcomes.all())
    assessments = list(offering.assessments.all())
    pos = list(ProgramOutcome.objects.all())

    current_aw = {
        (w.assessment_id, w.learning_outcome_id): w.weight
        for w in AssessmentLOWeight.objects.filter(assessment__offering=offering)
    }
    current_pw = {
        (w.learning_outcome_id, w.program_outcome_id): w.weight
        for w in LOPOWeight.objects.filter(learning_outcome__offering=offering)
    }

    assessment_rows = []
    for assessment in assessments:
        cells = []
        for lo in los:
            name = f"aw_{assessment.id}_{lo.id}"
            value = current_aw.get((assessment.id, lo.id), "")
            if assessment_values is not None:
                value = assessment_values.get(name, "")
            cells.append({"name": name, "value": value, "error": (assessment_errors or {}).get(name)})
        assessment_rows.append({"assessment": assessment, "cells": cells})

    po_rows = []
    for lo in los:
        cells = []
        for po in pos:
            name = f"pw_{lo.id}_{po.id}"
            value = current_pw.get((lo.id, po.id), "")
            if po_values is not None:
                value = po_values.get(name, "")
            cells.append({"name": name, "value": value, "error": (po_errors or {}).get(name)})
        po_rows.append({"lo": lo, "cells": cells})

    return {
        "offering": offering,
        "los": los,
        "assessments": assessments,
        "pos": pos,
        "assessment_rows": assessment_rows,
        "po_rows": po_rows,
    }


@role_required(User.Role.INSTRUCTOR)
def offering_setup(request, offering_id):
    offering = get_own_offering(request, offering_id)
    return render(request, "curriculum/offering_setup.html", build_setup_context(offering))


@role_required(User.Role.INSTRUCTOR)
def lo_form(request, offering_id, lo_id=None):
    """Add a learning outcome (no lo_id) or edit one."""
    offering = get_own_offering(request, offering_id)
    lo = get_object_or_404(LearningOutcome, pk=lo_id, offering=offering) if lo_id else None
    form = LearningOutcomeForm(request.POST or None, instance=lo)
    if request.method == "POST" and form.is_valid():
        form.instance.offering = offering
        try:
            with transaction.atomic():
                form.save()
        except IntegrityError:
            form.add_error("code", "This offering already has a learning outcome with that code.")
        else:
            messages.success(request, "Learning outcome saved.")
            return redirect("curriculum:offering_setup", offering_id=offering.id)
    return render(request, "curriculum/lo_form.html", {"offering": offering, "form": form, "lo": lo})


@role_required(User.Role.INSTRUCTOR)
def lo_delete(request, offering_id, lo_id):
    offering = get_own_offering(request, offering_id)
    lo = get_object_or_404(LearningOutcome, pk=lo_id, offering=offering)
    if request.method == "POST":
        with transaction.atomic():
            # Delete the weights first: their signals recompute the PO scores while this LO still exists.
            LOPOWeight.objects.filter(learning_outcome=lo).delete()
            AssessmentLOWeight.objects.filter(learning_outcome=lo).delete()
            lo.delete()
        refresh_department_stats()  # after the commit
        messages.success(request, f"Learning outcome {lo.code} deleted.")
        return redirect("curriculum:offering_setup", offering_id=offering.id)
    counts = {
        "assessment_weights": AssessmentLOWeight.objects.filter(learning_outcome=lo).count(),
        "po_weights": LOPOWeight.objects.filter(learning_outcome=lo).count(),
        "lo_scores": StudentLOScore.objects.filter(learning_outcome=lo).count(),
    }
    return render(request, "curriculum/lo_delete.html", {"offering": offering, "lo": lo, "counts": counts})


@role_required(User.Role.INSTRUCTOR)
def assessment_form(request, offering_id, assessment_id=None):
    """Add an assessment (no assessment_id) or rename one."""
    offering = get_own_offering(request, offering_id)
    assessment = get_object_or_404(Assessment, pk=assessment_id, offering=offering) if assessment_id else None
    form = AssessmentForm(request.POST or None, instance=assessment)
    if request.method == "POST" and form.is_valid():
        form.instance.offering = offering
        try:
            with transaction.atomic():
                form.save()
        except IntegrityError:
            form.add_error("name", "This offering already has an assessment with that name.")
        else:
            messages.success(request, "Assessment saved.")
            return redirect("curriculum:offering_setup", offering_id=offering.id)
    return render(
        request, "curriculum/assessment_form.html", {"offering": offering, "form": form, "assessment": assessment}
    )


@role_required(User.Role.INSTRUCTOR)
def assessment_delete(request, offering_id, assessment_id):
    offering = get_own_offering(request, offering_id)
    assessment = get_object_or_404(Assessment, pk=assessment_id, offering=offering)
    if request.method == "POST":
        with transaction.atomic():
            assessment.delete()
        refresh_department_stats()  # after the commit
        messages.success(request, f"Assessment {assessment.name} deleted.")
        return redirect("curriculum:offering_setup", offering_id=offering.id)
    grade_count = Grade.objects.filter(assessment=assessment).count()
    return render(
        request,
        "curriculum/assessment_delete.html",
        {"offering": offering, "assessment": assessment, "grade_count": grade_count},
    )


@role_required(User.Role.INSTRUCTOR)
@require_POST
def save_assessment_weights(request, offering_id):
    offering = get_own_offering(request, offering_id)
    context = build_setup_context(offering)
    parsed, errors, values = {}, {}, {}
    for row in context["assessment_rows"]:
        for cell in row["cells"]:
            raw = request.POST.get(cell["name"], "")
            values[cell["name"]] = raw
            weight, error = parse_assessment_weight(raw)
            if error:
                errors[cell["name"]] = error
            parsed[cell["name"]] = weight

    if errors:
        messages.error(request, "Nothing was saved. Please fix the highlighted weights.")
        context = build_setup_context(offering, assessment_values=values, assessment_errors=errors)
        return render(request, "curriculum/offering_setup.html", context)

    existing = {
        (w.assessment_id, w.learning_outcome_id): w
        for w in AssessmentLOWeight.objects.filter(assessment__offering=offering)
    }
    with transaction.atomic():
        for assessment in context["assessments"]:
            for lo in context["los"]:
                weight = parsed[f"aw_{assessment.id}_{lo.id}"]
                row = existing.get((assessment.id, lo.id))
                if weight is None:
                    if row:
                        row.delete()
                elif row is None:
                    AssessmentLOWeight.objects.create(assessment=assessment, learning_outcome=lo, weight=weight)
                elif row.weight != weight:
                    row.weight = weight
                    row.save()
    refresh_department_stats()  # after the commit
    messages.success(request, "Assessment weights saved and scores recalculated.")
    return redirect("curriculum:offering_setup", offering_id=offering.id)


@role_required(User.Role.INSTRUCTOR)
@require_POST
def save_po_weights(request, offering_id):
    offering = get_own_offering(request, offering_id)
    context = build_setup_context(offering)
    parsed, errors, values = {}, {}, {}
    for row in context["po_rows"]:
        for cell in row["cells"]:
            raw = request.POST.get(cell["name"], "")
            values[cell["name"]] = raw
            weight, error = parse_po_weight(raw)
            if error:
                errors[cell["name"]] = error
            parsed[cell["name"]] = weight

    if errors:
        messages.error(request, "Nothing was saved. Please fix the highlighted weights.")
        context = build_setup_context(offering, po_values=values, po_errors=errors)
        return render(request, "curriculum/offering_setup.html", context)

    existing = {
        (w.learning_outcome_id, w.program_outcome_id): w
        for w in LOPOWeight.objects.filter(learning_outcome__offering=offering)
    }
    with transaction.atomic():
        for lo in context["los"]:
            for po in context["pos"]:
                weight = parsed[f"pw_{lo.id}_{po.id}"]
                row = existing.get((lo.id, po.id))
                if weight is None:
                    if row:
                        row.delete()
                elif row is None:
                    LOPOWeight.objects.create(learning_outcome=lo, program_outcome=po, weight=weight)
                elif row.weight != weight:
                    row.weight = weight
                    row.save()
    refresh_department_stats()  # after the commit
    messages.success(request, "Program outcome weights saved and scores recalculated.")
    return redirect("curriculum:offering_setup", offering_id=offering.id)
