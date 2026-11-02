"""Keep the cached score tables in sync when grades or weights change."""

from django.core.exceptions import ObjectDoesNotExist
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from curriculum.models import AssessmentLOWeight, LOPOWeight
from grading.models import Enrollment, Grade
from scoring.recompute import recompute_offering, recompute_student


@receiver([post_save, post_delete], sender=Grade)
def grade_changed(sender, instance, **kwargs):
    try:
        student = instance.enrollment.student
    except ObjectDoesNotExist:  # parent already deleted by a cascade
        return
    recompute_student(student)


@receiver([post_save, post_delete], sender=Enrollment)
def enrollment_changed(sender, instance, **kwargs):
    try:
        student = instance.student
    except ObjectDoesNotExist:
        return
    recompute_student(student)


@receiver([post_save, post_delete], sender=AssessmentLOWeight)
def assessment_weight_changed(sender, instance, **kwargs):
    recompute_offering(instance.learning_outcome.offering)


@receiver([post_save, post_delete], sender=LOPOWeight)
def po_weight_changed(sender, instance, **kwargs):
    recompute_offering(instance.learning_outcome.offering)
