"""PO coverage page: numbers, statuses, term filter and permissions."""

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from curriculum.models import Course, CourseOffering, LearningOutcome, LOPOWeight, ProgramOutcome


class CoverageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)  # 3 offerings in 2026-Fall
        instructor = User.objects.get(username="instructor")
        # A second term: MAT241 again, feeding PO5 (so PO5 has 3 offerings in total) and PO8.
        offering = CourseOffering.objects.create(
            course=Course.objects.get(code="MAT241"), term="2027-Spring", instructor=instructor
        )
        lo = LearningOutcome.objects.create(offering=offering, code="LO1")
        LOPOWeight.objects.create(learning_outcome=lo, program_outcome=ProgramOutcome.objects.get(number=5), weight=2)
        LOPOWeight.objects.create(learning_outcome=lo, program_outcome=ProgramOutcome.objects.get(number=8), weight=5)

    def rows(self, **params):
        self.client.force_login(User.objects.get(username="head"))
        response = self.client.get(reverse("scoring:po_coverage"), params)
        self.assertEqual(response.status_code, 200)
        return {r["po"].number: r for r in response.context["rows"]}, response

    def test_all_11_pos_listed_with_counts(self):
        rows, _ = self.rows()
        self.assertEqual(sorted(rows), list(range(1, 12)))
        # PO1: CSE311 LO1 (2) and LO2 (1) -> one offering, two LOs, weight 3.
        self.assertEqual((rows[1]["offerings"], rows[1]["los"], rows[1]["weight_sum"]), (1, 2, 3))
        # PO5: CSE321 LO2 (4), MAT241 2026 LO1 (3), MAT241 2027 LO1 (2) -> three offerings.
        self.assertEqual((rows[5]["offerings"], rows[5]["los"], rows[5]["weight_sum"]), (3, 3, 9))
        self.assertEqual((rows[11]["offerings"], rows[11]["los"], rows[11]["weight_sum"]), (0, 0, 0))

    def test_statuses(self):
        rows, _ = self.rows()
        self.assertEqual(rows[11]["status"], "Not covered")
        self.assertEqual(rows[1]["status"], "Weak")  # only one offering
        self.assertEqual(rows[5]["status"], "Covered")

    def test_term_filter_limits_counts(self):
        rows, response = self.rows(term="2026-Fall")
        self.assertEqual(rows[5]["offerings"], 2)
        self.assertEqual(rows[8]["status"], "Not covered")  # PO8 only exists in 2027-Spring
        self.assertEqual(response.context["term"], "2026-Fall")
        rows, _ = self.rows(term="2027-Spring")
        self.assertEqual((rows[8]["offerings"], rows[8]["status"]), (1, "Weak"))
        self.assertEqual(rows[1]["status"], "Not covered")

    def test_term_select_lists_existing_terms_and_unknown_term_is_ignored(self):
        rows, response = self.rows()
        self.assertEqual(response.context["terms"], ["2027-Spring", "2026-Fall"])
        rows, response = self.rows(term="1999-Fall")
        self.assertEqual(response.context["term"], "")
        self.assertEqual(rows[5]["offerings"], 3)

    def test_one_query_for_all_pos(self):
        self.client.force_login(User.objects.get(username="head"))
        with self.assertNumQueries(4):  # session, user, list of terms, ONE annotated query for all 11 POs
            self.client.get(reverse("scoring:po_coverage"))

    def test_permissions(self):
        for username in ("instructor", "Batuhan"):
            self.client.force_login(User.objects.get(username=username))
            self.assertEqual(self.client.get(reverse("scoring:po_coverage")).status_code, 403, username)
        self.client.force_login(User.objects.get(username="admin"))
        self.assertEqual(self.client.get(reverse("scoring:po_coverage")).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("scoring:po_coverage")).status_code, 302)
