"""Tests for the reporting app. No test makes a real network call."""

from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from grading.models import Grade
from reporting import llm, rules, services
from reporting.models import PerformanceReport
from scoring.models import StudentPOScore


def row(number, score, incomplete=False, average=None):
    return {
        "number": number,
        "name": f"Outcome {number}",
        "score": None if score is None else Decimal(str(score)),
        "incomplete": incomplete,
        "department_average": None if average is None else Decimal(str(average)),
    }


class RulesTests(SimpleTestCase):
    def test_groups(self):
        rows = [
            row(1, 90, average=80),
            row(2, 80),
            row(3, 70, incomplete=True),
            row(4, 55, average=60),
            row(5, 40),
            row(6, 30),
            row(7, None),
        ]
        s = rules.summarize(rows)
        self.assertEqual([r["number"] for r in s["strongest"]], [1, 2, 3])
        self.assertEqual([r["number"] for r in s["weakest"]], [6, 5, 4])
        self.assertEqual([r["number"] for r in s["below_threshold"]], [4, 5, 6])
        self.assertEqual([r["number"] for r in s["incomplete"]], [3])
        self.assertEqual([r["number"] for r in s["no_score"]], [7])
        self.assertEqual({r["number"]: r["difference"] for r in s["comparison"]}, {1: 10, 4: -5})

    def test_threshold_is_exclusive(self):
        s = rules.summarize([row(1, 60), row(2, "59.9")])
        self.assertEqual([r["number"] for r in s["below_threshold"]], [2])

    def test_strongest_and_weakest_do_not_overlap(self):
        s = rules.summarize([row(1, 90), row(2, 50), row(3, 70)])
        self.assertEqual([r["number"] for r in s["strongest"]], [1])
        self.assertEqual([r["number"] for r in s["weakest"]], [2])

    def test_empty_and_all_missing(self):
        s = rules.summarize([row(1, None), row(2, None)])
        self.assertEqual(s["strongest"], [])
        self.assertEqual(s["weakest"], [])
        self.assertIn("No score yet", rules.summary_to_text(s))
        self.assertIn("no scores yet", rules.summary_to_text(rules.summarize([])))

    def test_text_rounds_to_one_decimal_only_in_text(self):
        rows = [row(1, "85.04567", average="80.0000"), row(2, "40.25"), row(3, 70)]
        s = rules.summarize(rows)
        self.assertEqual(s["strongest"][0]["score"], Decimal("85.04567"))
        text = rules.summary_to_text(s)
        self.assertIn("85.0", text)
        self.assertNotIn("85.04567", text)
        self.assertIn("below the threshold", text.lower())


class ReportTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        cls.batuhan = User.objects.get(username="Batuhan")
        cls.ali = User.objects.get(username="Ali")
        cls.head = User.objects.get(username="head")

    def login(self, username):
        self.client.force_login(User.objects.get(username=username))


@override_settings(GEMINI_API_KEY="test-key", GEMINI_MODEL="test-model")
class BuildReportTests(ReportTestBase):
    @mock.patch("reporting.llm.generate_text", return_value="Keep going.")
    def test_ai_commentary_is_stored(self, generate):
        report = services.build_report(self.batuhan, self.head)
        self.assertEqual(report.ai_commentary, "Keep going.")
        self.assertEqual(report.ai_model, "test-model")
        self.assertEqual(report.created_by, self.head)
        self.assertEqual(len(report.scores_snapshot), 11)
        self.assertTrue(report.summary_text)
        generate.assert_called_once()

    @mock.patch("reporting.llm.generate_text", side_effect=llm.LLMError("boom"))
    def test_ai_failure_still_stores_report(self, generate):
        report = services.build_report(self.batuhan, self.head)
        self.assertEqual(report.ai_commentary, "")
        self.assertEqual(report.ai_model, "")
        self.assertTrue(report.summary_text)

    @override_settings(GEMINI_API_KEY="")
    @mock.patch("reporting.llm.generate_text")
    def test_without_key_no_call_is_made(self, generate):
        report = services.build_report(self.batuhan, self.head)
        self.assertEqual(report.ai_commentary, "")
        generate.assert_not_called()

    @mock.patch("reporting.llm.generate_text", return_value="Keep going.")
    def test_unchanged_scores_reuse_report_without_api_call(self, generate):
        first = services.build_report(self.batuhan, self.head)
        second = services.build_report(self.batuhan, self.batuhan)
        self.assertEqual(first.id, second.id)
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(PerformanceReport.objects.filter(student=self.batuhan).count(), 1)

    @mock.patch("reporting.llm.generate_text", return_value="Keep going.")
    def test_changed_scores_create_new_report(self, generate):
        first = services.build_report(self.batuhan, self.head)
        grade = Grade.objects.filter(enrollment__student=self.batuhan).first()
        grade.score = Decimal("12")
        grade.save()  # signals refresh the cached PO scores
        second = services.build_report(self.batuhan, self.head)
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(generate.call_count, 2)

    @mock.patch("reporting.llm.generate_text", return_value="Keep going.")
    def test_other_students_changes_reuse_report_without_api_call(self, generate):
        first = services.build_report(self.batuhan, self.head)
        average_before = {r["number"]: r["department_average"] for r in services.collect_rows(self.batuhan)}
        grade = Grade.objects.filter(enrollment__student=self.ali).first()
        grade.score = Decimal("1")
        grade.save()  # only Ali's scores change, so the department averages move
        average_after = {r["number"]: r["department_average"] for r in services.collect_rows(self.batuhan)}
        self.assertNotEqual(average_before, average_after)
        second = services.build_report(self.batuhan, self.head)
        self.assertEqual(first.id, second.id)
        self.assertEqual(generate.call_count, 1)

    @override_settings(GEMINI_API_KEY="")
    @mock.patch("reporting.llm.generate_text")
    def test_report_without_commentary_is_reused_when_no_key(self, generate):
        first = services.build_report(self.batuhan, self.head)
        second = services.build_report(self.batuhan, self.head)
        self.assertEqual(first.id, second.id)
        generate.assert_not_called()

    @mock.patch("reporting.llm.generate_text", return_value="Now with AI.")
    def test_report_without_commentary_is_rebuilt_once_key_is_configured(self, generate):
        with override_settings(GEMINI_API_KEY=""):
            first = services.build_report(self.batuhan, self.head)
        self.assertEqual(first.ai_commentary, "")
        generate.assert_not_called()
        second = services.build_report(self.batuhan, self.head)
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(second.ai_commentary, "Now with AI.")
        generate.assert_called_once()
        third = services.build_report(self.batuhan, self.head)  # now it has commentary: reused
        self.assertEqual(second.id, third.id)
        generate.assert_called_once()

    @mock.patch("reporting.llm.generate_text", return_value="ok")
    def test_prompt_contains_no_personal_data(self, generate):
        services.build_report(self.batuhan, self.head)
        prompt = generate.call_args.args[0]
        for secret in (
            self.batuhan.username,
            self.batuhan.first_name,
            self.batuhan.last_name,
            self.batuhan.student_number,
            self.batuhan.email,
        ):
            self.assertTrue(secret)  # the seed data really sets all five
            self.assertNotIn(secret.lower(), prompt.lower())
        self.assertIn("PO1", prompt)
        self.assertIn("department average", prompt)
        self.assertIn("no score yet", prompt)  # PO8 has no data in the demo


@override_settings(GEMINI_API_KEY="")
class ReportViewTests(ReportTestBase):
    def test_anonymous_is_sent_to_login(self):
        response = self.client.get(reverse("reporting:my_report"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_student_sees_only_own_report(self):
        services.build_report(self.ali, self.head)
        self.login("Batuhan")
        response = self.client.get(reverse("reporting:my_report"))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["report"])  # Ali's report is not shown
        self.assertContains(response, "Generate report")
        self.client.post(reverse("reporting:my_report"))
        report = PerformanceReport.objects.get(student=self.batuhan)
        self.assertEqual(report.created_by, self.batuhan)
        response = self.client.get(reverse("reporting:my_report"), {"student": self.ali.id})
        self.assertEqual(response.context["report"], report)
        self.assertContains(response, "Refresh report")
        self.assertContains(response, "AI commentary is unavailable")

    def test_student_gets_403_on_head_pages(self):
        self.login("Batuhan")
        self.assertEqual(self.client.get(reverse("reporting:student_list")).status_code, 403)
        url = reverse("reporting:student_report", args=[self.ali.id])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertFalse(PerformanceReport.objects.exists())

    def test_instructor_gets_403(self):
        self.login("instructor")
        for name, args in [
            ("reporting:my_report", []),
            ("reporting:student_list", []),
            ("reporting:student_report", [self.ali.id]),
        ]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 403, name)

    def test_head_can_generate_and_view(self):
        self.login("head")
        url = reverse("reporting:student_report", args=[self.ali.id])
        self.assertRedirects(self.client.post(url), url, fetch_redirect_response=False)
        report = PerformanceReport.objects.get(student=self.ali)
        self.assertEqual(report.created_by, self.head)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Print / Save as PDF")
        self.assertEqual(len(response.context["rows"]), 11)
        self.assertEqual(self.client.get(reverse("reporting:student_list")).status_code, 200)

    def test_admin_can_open_list(self):
        self.login("admin")
        response = self.client.get(reverse("reporting:student_list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["students"]), 2)

    def test_non_student_id_is_404(self):
        self.login("head")
        for user in (self.head, User.objects.get(username="instructor")):
            self.assertEqual(self.client.get(reverse("reporting:student_report", args=[user.id])).status_code, 404)
        self.assertEqual(self.client.get(reverse("reporting:student_report", args=[999999])).status_code, 404)

    def test_ai_text_is_escaped(self):
        services.build_report(self.ali, self.head)
        PerformanceReport.objects.update(ai_commentary="<script>alert(1)</script>\nline two", ai_model="m")
        self.login("Ali")
        response = self.client.get(reverse("reporting:my_report"))
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")
        self.assertContains(response, "AI-generated commentary")

    def test_report_numbers_come_from_snapshot(self):
        report = services.build_report(self.ali, self.head)
        po1 = StudentPOScore.objects.get(student=self.ali, program_outcome__number=1)
        shown = next(r for r in report.scores_snapshot if r["number"] == 1)
        self.assertEqual(Decimal(shown["score"]), po1.score)
