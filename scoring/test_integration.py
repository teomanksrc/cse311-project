"""Database tests: the Elif example stored in the DB (LO->PO weights 2:1 instead of 1.0:0.5)."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import User
from curriculum.models import (
    Assessment,
    AssessmentLOWeight,
    Course,
    CourseOffering,
    LearningOutcome,
    LOPOWeight,
    ProgramOutcome,
)
from grading.models import Enrollment, Grade
from scoring.models import StudentLOScore, StudentPOScore


class ScoringFixtureMixin:
    @classmethod
    def build_cse311(cls):
        cls.instructor = User.objects.create_user("prof", role=User.Role.INSTRUCTOR)
        cls.po1 = ProgramOutcome.objects.create(number=1, short_name="PO1")
        cls.po2 = ProgramOutcome.objects.create(number=2, short_name="PO2")
        course = Course.objects.create(code="CSE311", name="Software")
        cls.offering = CourseOffering.objects.create(course=course, term="2026-Fall", instructor=cls.instructor)
        cls.lo1 = LearningOutcome.objects.create(offering=cls.offering, code="LO1")
        cls.lo2 = LearningOutcome.objects.create(offering=cls.offering, code="LO2")
        cls.midterm = Assessment.objects.create(offering=cls.offering, name="Midterm")
        cls.project = Assessment.objects.create(offering=cls.offering, name="Project")
        for assessment, lo, weight in [
            (cls.midterm, cls.lo1, "0.6"),
            (cls.midterm, cls.lo2, "0.4"),
            (cls.project, cls.lo1, "0.4"),
            (cls.project, cls.lo2, "1.0"),
        ]:
            AssessmentLOWeight.objects.create(assessment=assessment, learning_outcome=lo, weight=Decimal(weight))
        for lo, po, weight in [(cls.lo1, cls.po1, 2), (cls.lo2, cls.po1, 1), (cls.lo2, cls.po2, 2)]:
            LOPOWeight.objects.create(learning_outcome=lo, program_outcome=po, weight=weight)

    @classmethod
    def enroll(cls, username, midterm=None, project=None):
        student = User.objects.create_user(username, role=User.Role.STUDENT)
        enrollment = Enrollment.objects.create(student=student, offering=cls.offering)
        if midterm is not None:
            Grade.objects.create(enrollment=enrollment, assessment=cls.midterm, score=midterm)
        if project is not None:
            Grade.objects.create(enrollment=enrollment, assessment=cls.project, score=project)
        return student, enrollment

    def po_score(self, student, po):
        return StudentPOScore.objects.get(student=student, program_outcome=po)


class ElifIntegrationTests(ScoringFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.build_cse311()
        cls.elif_, cls.elif_enrollment = cls.enroll("elif", midterm=90, project=80)

    def test_elif_scores_are_computed_and_stored(self):
        lo1 = StudentLOScore.objects.get(enrollment=self.elif_enrollment, learning_outcome=self.lo1)
        lo2 = StudentLOScore.objects.get(enrollment=self.elif_enrollment, learning_outcome=self.lo2)
        self.assertEqual(round(lo1.score, 1), Decimal("86.0"))
        self.assertEqual(round(lo2.score, 1), Decimal("82.9"))
        self.assertEqual(round(self.po_score(self.elif_, self.po1).score, 1), Decimal("85.0"))
        self.assertEqual(round(self.po_score(self.elif_, self.po2).score, 1), Decimal("82.9"))
        self.assertFalse(self.po_score(self.elif_, self.po1).is_incomplete)

    def test_changing_a_grade_recomputes_scores(self):
        grade = Grade.objects.get(enrollment=self.elif_enrollment, assessment=self.project)
        grade.score = 100
        grade.save()
        self.assertGreater(self.po_score(self.elif_, self.po2).score, Decimal("90"))

    def test_changing_a_weight_recomputes_scores(self):
        link = LOPOWeight.objects.get(learning_outcome=self.lo2, program_outcome=self.po1)
        link.weight = 5
        link.save()
        expected = (Decimal("86") * 2 + (Decimal("90") * 4 + Decimal("80") * 10) / Decimal("14") * 5) / 7
        self.assertAlmostEqual(self.po_score(self.elif_, self.po1).score, expected, places=3)

    def test_missing_grade_marks_incomplete(self):
        student, _ = self.enroll("partial", midterm=70)
        self.assertTrue(self.po_score(student, self.po1).is_incomplete)

    def test_no_grades_produces_no_scores(self):
        student, _ = self.enroll("nograde")
        self.assertFalse(StudentPOScore.objects.filter(student=student).exists())

    def test_deleting_a_grade_removes_stale_scores(self):
        student, enrollment = self.enroll("onegrade", midterm=70)
        Grade.objects.filter(enrollment=enrollment).delete()
        self.assertFalse(StudentPOScore.objects.filter(student=student).exists())
        self.assertFalse(StudentLOScore.objects.filter(enrollment=enrollment).exists())


class MultiCourseDbTests(ScoringFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.build_cse311()
        cls.student, _ = cls.enroll("multi", midterm=90, project=80)
        mat = CourseOffering.objects.create(
            course=Course.objects.create(code="MAT241", name="Math"), term="2026-Fall", instructor=cls.instructor
        )
        lo = LearningOutcome.objects.create(offering=mat, code="LO1")
        exam = Assessment.objects.create(offering=mat, name="Final")
        AssessmentLOWeight.objects.create(assessment=exam, learning_outcome=lo, weight=1)
        LOPOWeight.objects.create(learning_outcome=lo, program_outcome=cls.po2, weight=2)
        enrollment = Enrollment.objects.create(student=cls.student, offering=mat)
        Grade.objects.create(enrollment=enrollment, assessment=exam, score=60)

    def test_po2_combines_both_courses(self):
        # CSE311 LO2 (82.857, weight 2) and MAT241 LO1 (60, weight 2)
        expected = (Decimal("82.857142857") * 2 + 60 * 2) / 4
        self.assertAlmostEqual(self.po_score(self.student, self.po2).score, expected, places=2)


class DatabaseConstraintTests(ScoringFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.build_cse311()
        cls.student, cls.enrollment = cls.enroll("elif", midterm=90)

    def assert_db_rejects(self, create):
        with self.assertRaises(IntegrityError), transaction.atomic():
            create()

    def test_grade_out_of_range_rejected(self):
        self.assert_db_rejects(
            lambda: Grade.objects.create(enrollment=self.enrollment, assessment=self.project, score=101)
        )

    def test_duplicate_grade_rejected(self):
        self.assert_db_rejects(
            lambda: Grade.objects.create(enrollment=self.enrollment, assessment=self.midterm, score=50)
        )

    def test_lo_po_weight_must_be_1_to_5(self):
        for bad in (0, 6):
            self.assert_db_rejects(
                lambda bad=bad: LOPOWeight.objects.create(
                    learning_outcome=self.lo1, program_outcome=self.po2, weight=bad
                )
            )

    def test_duplicate_lo_po_link_rejected(self):
        self.assert_db_rejects(
            lambda: LOPOWeight.objects.create(learning_outcome=self.lo1, program_outcome=self.po1, weight=3)
        )

    def test_non_positive_assessment_weight_rejected(self):
        extra = Assessment.objects.create(offering=self.offering, name="Quiz")
        self.assert_db_rejects(
            lambda: AssessmentLOWeight.objects.create(assessment=extra, learning_outcome=self.lo1, weight=0)
        )

    def test_clean_rejects_cross_offering_link(self):
        other = CourseOffering.objects.create(
            course=Course.objects.create(code="CSE321", name="Data"), term="2026-Fall", instructor=self.instructor
        )
        other_lo = LearningOutcome.objects.create(offering=other, code="LO1")
        link = AssessmentLOWeight(assessment=self.midterm, learning_outcome=other_lo, weight=1)
        with self.assertRaises(ValidationError):
            link.clean()
