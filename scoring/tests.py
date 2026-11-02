"""Unit tests for the pure scoring service (no database)."""

from decimal import Decimal

from django.test import SimpleTestCase

from scoring import services

# Reference example from the project guidelines (slides 5-6).
ASSESSMENT_TO_LO = {
    "LO1": [("midterm", Decimal("0.6")), ("project", Decimal("0.4"))],
    "LO2": [("midterm", Decimal("0.4")), ("project", Decimal("1.0"))],
}
LO_TO_PO = {
    "PO1": [("LO1", Decimal("1.0")), ("LO2", Decimal("0.5"))],
    "PO2": [("LO2", Decimal("1.0"))],
}


def run_chain(grades):
    lo = {name: services.compute_lo_score(src, grades) for name, src in ASSESSMENT_TO_LO.items()}
    lo = {name: result for name, result in lo.items() if result is not None}
    po = {name: services.compute_po_score(src, lo) for name, src in LO_TO_PO.items()}
    return lo, po


class ElifReferenceExampleTests(SimpleTestCase):
    def test_elif_matches_slide_values(self):
        lo, po = run_chain({"midterm": 90, "project": 80})
        self.assertEqual(lo["LO1"].rounded(), Decimal("86.0"))
        self.assertEqual(lo["LO2"].rounded(), Decimal("82.9"))
        self.assertEqual(po["PO1"].rounded(), Decimal("85.0"))
        self.assertEqual(po["PO2"].rounded(), Decimal("82.9"))
        self.assertFalse(any(r.is_incomplete for r in (*lo.values(), *po.values())))

    def test_second_student(self):
        lo, po = run_chain({"midterm": 100, "project": 90})
        self.assertEqual(lo["LO1"].rounded(), Decimal("96.0"))
        self.assertEqual(lo["LO2"].rounded(), Decimal("92.9"))
        self.assertEqual(po["PO1"].rounded(), Decimal("95.0"))
        self.assertEqual(po["PO2"].rounded(), Decimal("92.9"))

    def test_full_precision_is_kept_internally(self):
        lo, _ = run_chain({"midterm": 90, "project": 80})
        self.assertNotEqual(lo["LO2"].score, lo["LO2"].rounded())


class MultiCourseAggregationTests(SimpleTestCase):
    def test_po_combines_los_from_different_courses(self):
        lo_results = {
            ("cse311", "LO1"): services.ScoreResult(Decimal("80")),
            ("mat241", "LO1"): services.ScoreResult(Decimal("60")),
        }
        sources = [(("cse311", "LO1"), 3), (("mat241", "LO1"), 1)]
        result = services.compute_po_score(sources, lo_results)
        self.assertEqual(result.score, Decimal("75"))  # (3*80 + 1*60) / 4
        self.assertFalse(result.is_incomplete)


class MissingGradeTests(SimpleTestCase):
    def test_partial_grades_are_incomplete_and_use_available_ones(self):
        result = services.compute_lo_score(ASSESSMENT_TO_LO["LO2"], {"midterm": 90})
        self.assertEqual(result.score, Decimal("90"))  # only the midterm counts
        self.assertTrue(result.is_incomplete)

    def test_no_grades_gives_no_lo_score(self):
        self.assertIsNone(services.compute_lo_score(ASSESSMENT_TO_LO["LO1"], {}))

    def test_incomplete_lo_makes_po_incomplete(self):
        lo, po = run_chain({"midterm": 90})
        self.assertTrue(lo["LO1"].is_incomplete)
        self.assertTrue(po["PO1"].is_incomplete)
        self.assertTrue(po["PO2"].is_incomplete)

    def test_lo_without_score_is_excluded_and_po_is_incomplete(self):
        lo_results = {"LO1": services.ScoreResult(Decimal("80"))}
        result = services.compute_po_score([("LO1", 1), ("LO2", 1)], lo_results)
        self.assertEqual(result.score, Decimal("80"))
        self.assertTrue(result.is_incomplete)

    def test_po_without_any_lo_score_is_none(self):
        self.assertIsNone(services.compute_po_score([("LO1", 1)], {}))

    def test_zero_is_a_real_grade_not_missing(self):
        result = services.compute_lo_score([("a", 1), ("b", 1)], {"a": 0, "b": 100})
        self.assertEqual(result.score, Decimal("50"))
        self.assertFalse(result.is_incomplete)


class ValidationTests(SimpleTestCase):
    def test_zero_or_negative_weight_is_rejected(self):
        for bad in (0, -1, Decimal("-0.5")):
            with self.assertRaises(ValueError):
                services.compute_lo_score([("a", bad)], {"a": 50})

    def test_out_of_range_grade_is_rejected(self):
        for bad in (-1, 100.5, 101):
            with self.assertRaises(ValueError):
                services.compute_lo_score([("a", 1)], {"a": bad})
