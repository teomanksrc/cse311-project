from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from curriculum.models import (
    Assessment,
    AssessmentLOWeight,
    CourseOffering,
    LearningOutcome,
    LOPOWeight,
    ProgramOutcome,
)
from grading.models import Grade
from scoring.models import StudentPOScore


class SetupTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        cls.offering = CourseOffering.objects.get(course__code="CSE311")
        cls.lo1 = LearningOutcome.objects.get(offering=cls.offering, code="LO1")
        cls.lo2 = LearningOutcome.objects.get(offering=cls.offering, code="LO2")
        cls.midterm = Assessment.objects.get(offering=cls.offering, name="Midterm")
        cls.project = Assessment.objects.get(offering=cls.offering, name="Project")
        cls.batuhan = User.objects.get(username="Batuhan")

    def setUp(self):
        self.client.force_login(User.objects.get(username="instructor"))

    def url(self, name, *args):
        return reverse(f"curriculum:{name}", args=[self.offering.id, *args])

    def po_score(self, number):
        return StudentPOScore.objects.get(student=self.batuhan, program_outcome__number=number).score

    def current_assessment_cells(self):
        """POST data that reproduces the current assessment grid."""
        data = {}
        for assessment in (self.midterm, self.project):
            for lo in (self.lo1, self.lo2):
                data[f"aw_{assessment.id}_{lo.id}"] = ""
        for w in AssessmentLOWeight.objects.filter(assessment__offering=self.offering):
            data[f"aw_{w.assessment_id}_{w.learning_outcome_id}"] = str(w.weight)
        return data

    def current_po_cells(self):
        data = {f"pw_{lo.id}_{po.id}": "" for lo in (self.lo1, self.lo2) for po in ProgramOutcome.objects.all()}
        for w in LOPOWeight.objects.filter(learning_outcome__offering=self.offering):
            data[f"pw_{w.learning_outcome_id}_{w.program_outcome_id}"] = str(w.weight)
        return data


class PermissionTests(SetupTestBase):
    def all_urls(self):
        return [
            self.url("offering_setup"),
            self.url("lo_create"),
            self.url("lo_edit", self.lo1.id),
            self.url("lo_delete", self.lo1.id),
            self.url("assessment_create"),
            self.url("assessment_edit", self.midterm.id),
            self.url("assessment_delete", self.midterm.id),
            self.url("assessment_weights"),
            self.url("po_weights"),
        ]

    def test_anonymous_redirected_and_student_forbidden(self):
        self.client.logout()
        for url in self.all_urls():
            self.assertEqual(self.client.get(url).status_code, 302, url)
        self.client.force_login(self.batuhan)
        for url in self.all_urls():
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_other_instructor_gets_404_and_changes_nothing(self):
        other = User.objects.create_user("other", password="x", role=User.Role.INSTRUCTOR)
        self.client.force_login(other)
        for url in self.all_urls():
            self.assertEqual(self.client.post(url, {}).status_code, 404, url)
        self.assertEqual(self.client.get(self.url("offering_setup")).status_code, 404)
        self.assertEqual(self.client.post(self.url("lo_delete", self.lo1.id)).status_code, 404)
        self.assertEqual(self.client.post(self.url("assessment_weights"), {}).status_code, 404)
        self.assertTrue(LearningOutcome.objects.filter(pk=self.lo1.id).exists())

    def test_weight_saves_require_post(self):
        self.assertEqual(self.client.get(self.url("assessment_weights")).status_code, 405)
        self.assertEqual(self.client.get(self.url("po_weights")).status_code, 405)

    def test_page_shows_current_values(self):
        response = self.client.get(self.url("offering_setup"))
        self.assertContains(response, f'name="aw_{self.midterm.id}_{self.lo1.id}" value="0.60"')


class LearningOutcomeTests(SetupTestBase):
    def test_add_edit_and_duplicate_code(self):
        response = self.client.post(self.url("lo_create"), {"code": "LO3", "description": "New"})
        self.assertRedirects(response, self.url("offering_setup"))
        lo3 = LearningOutcome.objects.get(offering=self.offering, code="LO3")
        self.client.post(self.url("lo_edit", lo3.id), {"code": "LO3", "description": "Changed"})
        lo3.refresh_from_db()
        self.assertEqual(lo3.description, "Changed")
        response = self.client.post(self.url("lo_create"), {"code": "LO1", "description": "dup"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already has a learning outcome")
        self.assertEqual(LearningOutcome.objects.filter(offering=self.offering, code="LO1").count(), 1)

    def test_delete_confirmation_and_delete(self):
        response = self.client.get(self.url("lo_delete", self.lo2.id))
        self.assertContains(response, "program outcome weight(s)")
        self.assertTrue(LearningOutcome.objects.filter(pk=self.lo2.id).exists())
        before = self.po_score(1)
        self.client.post(self.url("lo_delete", self.lo2.id))
        self.assertFalse(LearningOutcome.objects.filter(pk=self.lo2.id).exists())
        # PO2 was fed only by LO2 of this course, so it has no score any more.
        self.assertFalse(StudentPOScore.objects.filter(student=self.batuhan, program_outcome__number=2).exists())
        self.assertNotEqual(self.po_score(1), before)


class AssessmentTests(SetupTestBase):
    def test_add_rename_and_duplicate_name(self):
        self.client.post(self.url("assessment_create"), {"name": "Quiz"})
        quiz = Assessment.objects.get(offering=self.offering, name="Quiz")
        self.client.post(self.url("assessment_edit", quiz.id), {"name": "Quiz 1"})
        quiz.refresh_from_db()
        self.assertEqual(quiz.name, "Quiz 1")
        response = self.client.post(self.url("assessment_create"), {"name": "Midterm"})
        self.assertContains(response, "already has an assessment")

    def test_delete_shows_grade_count_and_removes_grades(self):
        response = self.client.get(self.url("assessment_delete", self.midterm.id))
        self.assertContains(response, "remove 2 grade(s)")
        before = self.po_score(1)
        self.client.post(self.url("assessment_delete", self.midterm.id))
        self.assertFalse(Assessment.objects.filter(pk=self.midterm.id).exists())
        self.assertFalse(Grade.objects.filter(assessment_id=self.midterm.id).exists())
        self.assertNotEqual(self.po_score(1), before)


class AssessmentWeightGridTests(SetupTestBase):
    def test_edit_changes_po_scores(self):
        before = self.po_score(1)
        data = self.current_assessment_cells()
        data[f"aw_{self.midterm.id}_{self.lo1.id}"] = "5"  # midterm (90) now dominates LO1
        response = self.client.post(self.url("assessment_weights"), data)
        self.assertRedirects(response, self.url("offering_setup"))
        self.assertEqual(AssessmentLOWeight.objects.get(assessment=self.midterm, learning_outcome=self.lo1).weight, 5)
        self.assertGreater(self.po_score(1), before)

    def test_blank_deletes_link_and_new_link_creates(self):
        data = self.current_assessment_cells()
        data[f"aw_{self.project.id}_{self.lo1.id}"] = ""
        data[f"aw_{self.midterm.id}_{self.lo2.id}"] = "0.25"
        self.client.post(self.url("assessment_weights"), data)
        self.assertFalse(AssessmentLOWeight.objects.filter(assessment=self.project, learning_outcome=self.lo1).exists())
        self.assertEqual(
            AssessmentLOWeight.objects.get(assessment=self.midterm, learning_outcome=self.lo2).weight, Decimal("0.25")
        )

    def test_invalid_cell_saves_nothing_and_shows_errors(self):
        before = list(AssessmentLOWeight.objects.order_by("id").values_list("id", "weight"))
        data = self.current_assessment_cells()
        data[f"aw_{self.midterm.id}_{self.lo1.id}"] = "9"  # valid, must not be saved
        data[f"aw_{self.project.id}_{self.lo1.id}"] = "-1"
        data[f"aw_{self.project.id}_{self.lo2.id}"] = "abc"
        response = self.client.post(self.url("assessment_weights"), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Must be greater than 0")
        self.assertContains(response, "Not a number")
        self.assertContains(response, 'value="9"')  # entered value is kept
        self.assertEqual(list(AssessmentLOWeight.objects.order_by("id").values_list("id", "weight")), before)

    def test_zero_nan_and_too_many_decimals_rejected(self):
        for bad in ("0", "NaN", "Infinity", "1.234", "100000"):
            data = self.current_assessment_cells()
            data[f"aw_{self.midterm.id}_{self.lo1.id}"] = bad
            response = self.client.post(self.url("assessment_weights"), data)
            self.assertEqual(response.status_code, 200, bad)

    def test_unchanged_grid_does_not_recompute(self):
        with mock.patch("scoring.signals.recompute_offering") as recompute:
            self.client.post(self.url("assessment_weights"), self.current_assessment_cells())
        recompute.assert_not_called()


class POWeightGridTests(SetupTestBase):
    def test_edit_changes_po_scores(self):
        po1 = ProgramOutcome.objects.get(number=1)
        before = self.po_score(1)
        data = self.current_po_cells()
        data[f"pw_{self.lo1.id}_{po1.id}"] = "1"  # LO1 now counts less towards PO1
        response = self.client.post(self.url("po_weights"), data)
        self.assertRedirects(response, self.url("offering_setup"))
        self.assertEqual(LOPOWeight.objects.get(learning_outcome=self.lo1, program_outcome=po1).weight, 1)
        self.assertNotEqual(self.po_score(1), before)

    def test_new_link_and_blank_delete(self):
        po8 = ProgramOutcome.objects.get(number=8)
        po2 = ProgramOutcome.objects.get(number=2)
        self.assertFalse(StudentPOScore.objects.filter(student=self.batuhan, program_outcome=po8).exists())
        data = self.current_po_cells()
        data[f"pw_{self.lo1.id}_{po8.id}"] = "3"
        data[f"pw_{self.lo2.id}_{po2.id}"] = ""
        self.client.post(self.url("po_weights"), data)
        self.assertTrue(StudentPOScore.objects.filter(student=self.batuhan, program_outcome=po8).exists())
        self.assertFalse(StudentPOScore.objects.filter(student=self.batuhan, program_outcome=po2).exists())

    def test_invalid_cells_save_nothing(self):
        before = list(LOPOWeight.objects.order_by("id").values_list("id", "weight"))
        po1 = ProgramOutcome.objects.get(number=1)
        po3 = ProgramOutcome.objects.get(number=3)
        data = self.current_po_cells()
        data[f"pw_{self.lo1.id}_{po1.id}"] = "5"
        data[f"pw_{self.lo1.id}_{po3.id}"] = "6"
        data[f"pw_{self.lo2.id}_{po3.id}"] = "2.5"
        response = self.client.post(self.url("po_weights"), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Must be 1-5")
        self.assertContains(response, "Whole number 1-5")
        self.assertEqual(list(LOPOWeight.objects.order_by("id").values_list("id", "weight")), before)
