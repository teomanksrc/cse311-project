"""Tests for the syllabus feature. No test makes a real network call: the Gemini client is always mocked."""

from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from pypdf import PdfWriter

from accounts.models import User
from curriculum import syllabus
from curriculum.models import (
    Assessment,
    AssessmentLOWeight,
    CourseOffering,
    LearningOutcome,
    LOPOWeight,
    ProgramOutcome,
)
from reporting import llm

PO_NUMBERS = set(range(1, 12))


def good_reply():
    return {
        "learning_outcomes": [
            {"code": "LO1", "description": "Explain things", "po_links": [{"po": 3, "weight": 4}]},
            {
                "code": "LO2",
                "description": "Build things",
                "po_links": [{"po": 1, "weight": 5}, {"po": 2, "weight": 1}],
            },
        ],
        "assessments": [
            {"name": "Midterm", "lo_weights": [{"lo": "LO1", "weight": 60}, {"lo": "LO2", "weight": "0.5"}]},
            {"name": "Final", "lo_weights": [{"lo": "LO2", "weight": 40.25}]},
        ],
    }


class ValidateProposalTests(SimpleTestCase):
    def validate(self, data, existing=()):
        return syllabus.validate_proposal(data, PO_NUMBERS, existing)

    def test_good_reply(self):
        proposal, errors = self.validate(good_reply())
        self.assertEqual(errors, [])
        self.assertEqual(proposal["warnings"], [])
        self.assertEqual([lo["code"] for lo in proposal["learning_outcomes"]], ["LO1", "LO2"])
        self.assertEqual(proposal["learning_outcomes"][1]["po_links"], [{"po": 1, "weight": 5}, {"po": 2, "weight": 1}])
        midterm = proposal["assessments"][0]
        self.assertEqual(midterm["lo_weights"], [{"lo": "LO1", "weight": "60"}, {"lo": "LO2", "weight": "0.5"}])
        self.assertEqual(proposal["assessments"][1]["lo_weights"], [{"lo": "LO2", "weight": "40.25"}])

    def test_strings_are_trimmed(self):
        proposal, errors = self.validate(
            {"learning_outcomes": [{"code": "  LO1 ", "description": " d "}], "assessments": [{"name": " Quiz "}]}
        )
        self.assertEqual(errors, [])
        self.assertEqual(proposal["learning_outcomes"][0]["code"], "LO1")
        self.assertEqual(proposal["learning_outcomes"][0]["description"], "d")
        self.assertEqual(proposal["assessments"][0]["name"], "Quiz")

    def test_wrong_types(self):
        for reply in (None, [], "text", 5):
            proposal, errors = self.validate(reply)
            self.assertIsNone(proposal)
            self.assertTrue(errors)
        proposal, errors = self.validate({"learning_outcomes": "x", "assessments": {"a": 1}})
        self.assertIsNone(proposal)
        self.assertTrue(errors)

    def test_wrong_item_types_are_dropped_with_warnings(self):
        reply = {
            "learning_outcomes": [
                "LO1",
                {"code": 5},
                {"code": ""},
                {"code": "x" * 21},
                {"code": "LO1", "description": 7},
            ],
            "assessments": [None, {"name": ["a"]}, {"name": "y" * 101}, {"name": "Quiz", "lo_weights": "bad"}],
        }
        proposal, errors = self.validate(reply)
        self.assertEqual(errors, [])
        self.assertEqual(proposal["learning_outcomes"], [{"code": "LO1", "description": "", "po_links": []}])
        self.assertEqual(proposal["assessments"], [{"name": "Quiz", "lo_weights": []}])
        self.assertEqual(len(proposal["warnings"]), 7)

    def test_bad_po_weights_are_dropped(self):
        links = [
            {"po": 1, "weight": 0},
            {"po": 2, "weight": 6},
            {"po": 3, "weight": 2.5},
            {"po": 4, "weight": "3"},
            {"po": 5, "weight": True},
            {"po": 6, "weight": None},
            {"po": 7, "weight": 3.0},  # a whole float is accepted as 3
        ]
        proposal, errors = self.validate({"learning_outcomes": [{"code": "LO1", "po_links": links}]})
        self.assertEqual(errors, [])
        self.assertEqual(proposal["learning_outcomes"][0]["po_links"], [{"po": 7, "weight": 3}])
        self.assertEqual(len(proposal["warnings"]), 6)

    def test_bad_assessment_weights_are_dropped(self):
        weights = [0, -1, "abc", 1.234, 10000, 99999, True, None, [1], float("inf"), "nan"]
        links = [{"lo": "LO1", "weight": w} for w in weights]
        reply = {
            "learning_outcomes": [{"code": "LO1"}],
            "assessments": [{"name": "Quiz", "lo_weights": links}],
        }
        proposal, errors = self.validate(reply)
        self.assertEqual(errors, [])
        self.assertEqual(proposal["assessments"][0]["lo_weights"], [])
        self.assertEqual(len(proposal["warnings"]), len(weights))

    def test_largest_allowed_assessment_weight(self):
        reply = {
            "learning_outcomes": [{"code": "LO1"}],
            "assessments": [{"name": "Q", "lo_weights": [{"lo": "LO1", "weight": "9999.99"}]}],
        }
        proposal, _ = self.validate(reply)
        self.assertEqual(proposal["assessments"][0]["lo_weights"][0]["weight"], "9999.99")

    def test_unknown_po_is_dropped(self):
        links = [{"po": 99, "weight": 3}, {"po": "3", "weight": 3}, {"po": [1], "weight": 3}, {"weight": 3}]
        proposal, errors = self.validate({"learning_outcomes": [{"code": "LO1", "po_links": links}]})
        self.assertEqual(errors, [])
        self.assertEqual(proposal["learning_outcomes"][0]["po_links"], [])
        self.assertEqual(len(proposal["warnings"]), 4)

    def test_unknown_lo_code_is_dropped_but_existing_lo_is_allowed(self):
        reply = {
            "learning_outcomes": [{"code": "LO1"}],
            "assessments": [{"name": "Quiz", "lo_weights": [{"lo": "LO9", "weight": 1}, {"lo": "LO1", "weight": 1}]}],
        }
        proposal, _ = self.validate(reply)
        self.assertEqual(proposal["assessments"][0]["lo_weights"], [{"lo": "LO1", "weight": "1"}])
        self.assertEqual(len(proposal["warnings"]), 1)
        reply["assessments"][0]["lo_weights"] = [{"lo": "LO9", "weight": 1}]
        proposal, _ = self.validate(reply, existing=["LO9"])
        self.assertEqual(proposal["assessments"][0]["lo_weights"], [{"lo": "LO9", "weight": "1"}])
        self.assertEqual(proposal["warnings"], [])

    def test_duplicates_are_dropped(self):
        reply = {
            "learning_outcomes": [
                {"code": "LO1", "po_links": [{"po": 1, "weight": 2}, {"po": 1, "weight": 3}]},
                {"code": "LO1"},
            ],
            "assessments": [
                {"name": "Quiz", "lo_weights": [{"lo": "LO1", "weight": 1}, {"lo": "LO1", "weight": 2}]},
                {"name": "Quiz"},
            ],
        }
        proposal, errors = self.validate(reply)
        self.assertEqual(errors, [])
        self.assertEqual(len(proposal["learning_outcomes"]), 1)
        self.assertEqual(proposal["learning_outcomes"][0]["po_links"], [{"po": 1, "weight": 2}])
        self.assertEqual(len(proposal["assessments"]), 1)
        self.assertEqual(proposal["assessments"][0]["lo_weights"], [{"lo": "LO1", "weight": "1"}])
        self.assertEqual(len(proposal["warnings"]), 4)

    def test_too_many_items_are_capped(self):
        reply = {
            "learning_outcomes": [{"code": f"LO{i}"} for i in range(syllabus.MAX_LOS + 5)],
            "assessments": [{"name": f"A{i}"} for i in range(syllabus.MAX_ASSESSMENTS + 5)],
        }
        proposal, errors = self.validate(reply)
        self.assertEqual(errors, [])
        self.assertEqual(len(proposal["learning_outcomes"]), syllabus.MAX_LOS)
        self.assertEqual(len(proposal["assessments"]), syllabus.MAX_ASSESSMENTS)
        self.assertEqual(len(proposal["warnings"]), 2)

    def test_empty_reply_is_an_error(self):
        for reply in (
            {},
            {"learning_outcomes": [], "assessments": []},
            {"learning_outcomes": [5], "assessments": [None]},
        ):
            proposal, errors = self.validate(reply)
            self.assertIsNone(proposal)
            self.assertTrue(errors)

    def test_only_assessments_is_usable(self):
        proposal, errors = self.validate({"assessments": [{"name": "Quiz"}]})
        self.assertEqual(errors, [])
        self.assertEqual(proposal["learning_outcomes"], [])


def tiny_pdf(text):
    """A one-page PDF with the given text, written by hand (pypdf can read it back)."""
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 100] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        None,
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream = f"BT /F1 12 Tf 10 50 Td ({text}) Tj ET"
    objects[3] = f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"
    out = "%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n"
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    return out.encode("latin-1")


class ExtractTextTests(SimpleTestCase):
    def test_txt(self):
        self.assertEqual(syllabus.extract_text("Syllabus.TXT", "  Merhaba dünya \n".encode("utf-8")), "Merhaba dünya")

    def test_txt_not_utf8(self):
        with self.assertRaises(ValueError):
            syllabus.extract_text("a.txt", "dünya".encode("cp1254"))

    def test_empty_txt(self):
        with self.assertRaises(ValueError):
            syllabus.extract_text("a.txt", b"   \n")

    def test_unsupported_extension(self):
        with self.assertRaises(ValueError):
            syllabus.extract_text("a.docx", b"x")

    def test_pdf_with_text(self):
        self.assertIn("Learning outcomes", syllabus.extract_text("a.pdf", tiny_pdf("Learning outcomes")))

    def test_pdf_without_text(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        import io

        buffer = io.BytesIO()
        writer.write(buffer)
        with self.assertRaisesMessage(ValueError, "No text"):
            syllabus.extract_text("blank.pdf", buffer.getvalue())

    def test_broken_pdf(self):
        with self.assertRaises(ValueError):
            syllabus.extract_text("a.pdf", b"this is not a pdf")


class BuildPromptTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def test_prompt_lists_pos_and_caps_text(self):
        prompt = syllabus.build_prompt("A" * 40000, ProgramOutcome.objects.all())
        self.assertIn("PO1:", prompt)
        self.assertIn("PO11:", prompt)
        self.assertIn("A" * syllabus.MAX_TEXT_CHARS, prompt)
        self.assertNotIn("A" * (syllabus.MAX_TEXT_CHARS + 1), prompt)


@override_settings(GEMINI_API_KEY="test-key")
class SyllabusViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        cls.offering = CourseOffering.objects.get(course__code="CSE311")
        cls.instructor = User.objects.get(username="instructor")
        cls.lo1 = LearningOutcome.objects.get(offering=cls.offering, code="LO1")
        cls.midterm = Assessment.objects.get(offering=cls.offering, name="Midterm")

    def setUp(self):
        self.client.force_login(self.instructor)

    def url(self, name):
        return reverse(f"curriculum:{name}", args=[self.offering.id])

    def counts(self):
        return (
            LearningOutcome.objects.count(),
            Assessment.objects.count(),
            LOPOWeight.objects.count(),
            AssessmentLOWeight.objects.count(),
        )

    def upload(self, reply=None, **kwargs):
        with mock.patch("reporting.llm.generate_json", return_value=reply or good_reply(), **kwargs) as generate:
            response = self.client.post(self.url("syllabus_upload"), {"text": "Course about things."})
        return response, generate

    def test_upload_page_loads_and_is_enabled(self):
        response = self.client.get(self.url("syllabus_upload"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "not configured")
        self.assertNotContains(response, "<fieldset disabled")

    @override_settings(GEMINI_API_KEY="")
    def test_disabled_without_api_key(self):
        response = self.client.get(self.url("syllabus_upload"))
        self.assertContains(response, "not configured")
        self.assertContains(response, "<fieldset disabled")
        with mock.patch("reporting.llm.generate_json") as generate:
            response = self.client.post(self.url("syllabus_upload"), {"text": "Course"})
        generate.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(f"syllabus_proposal_{self.offering.id}", self.client.session)

    def test_happy_path_upload_review_apply(self):
        before = self.counts()
        response, generate = self.upload()
        self.assertRedirects(response, self.url("syllabus_review"))
        prompt = generate.call_args.args[0]
        self.assertIn("Course about things.", prompt)
        self.assertEqual(self.counts(), before)  # nothing is written before Apply

        response = self.client.get(self.url("syllabus_review"))
        self.assertContains(response, "Explain things")
        self.assertContains(response, "already exists, will be skipped")  # LO1 and Midterm exist
        self.assertContains(response, "Apply")
        self.assertEqual(self.counts(), before)

        # Existing rows must stay exactly as they are.
        lo1_description = self.lo1.description
        old_midterm_weights = list(
            AssessmentLOWeight.objects.filter(assessment=self.midterm).values_list("learning_outcome_id", "weight")
        )
        old_lo1_po = sorted(
            LOPOWeight.objects.filter(learning_outcome=self.lo1).values_list("program_outcome_id", "weight")
        )

        with mock.patch("curriculum.views.refresh_department_stats") as refresh:
            response = self.client.post(self.url("syllabus_apply"))
        self.assertRedirects(response, self.url("offering_setup"))
        refresh.assert_called_once()
        self.assertNotIn(f"syllabus_proposal_{self.offering.id}", self.client.session)

        # LO1, LO2 and Midterm exist already in the demo; only "Final" and new links are created.
        final = Assessment.objects.get(offering=self.offering, name="Final")
        self.assertEqual(AssessmentLOWeight.objects.get(assessment=final).weight, 40.25)
        self.lo1.refresh_from_db()
        self.assertEqual(self.lo1.description, lo1_description)
        for lo_id, weight in old_midterm_weights:
            self.assertEqual(
                AssessmentLOWeight.objects.get(assessment=self.midterm, learning_outcome_id=lo_id).weight, weight
            )
        for po_id, weight in old_lo1_po:
            self.assertEqual(LOPOWeight.objects.get(learning_outcome=self.lo1, program_outcome_id=po_id).weight, weight)
        self.assertEqual(Assessment.objects.filter(offering=self.offering).count(), 3)

    def test_apply_creates_everything_in_an_empty_offering(self):
        empty = CourseOffering.objects.create(
            course=self.offering.course, term="2030-Spring", instructor=self.instructor
        )
        with mock.patch("reporting.llm.generate_json", return_value=good_reply()):
            self.client.post(reverse("curriculum:syllabus_upload", args=[empty.id]), {"text": "x"})
        with mock.patch("curriculum.views.refresh_department_stats"):
            response = self.client.post(reverse("curriculum:syllabus_apply", args=[empty.id]), follow=True)
        self.assertContains(
            response, "Applied: 2 learning outcomes, 2 assessments, 3 LO-PO weights and 3 assessment-LO weights"
        )
        self.assertEqual(LearningOutcome.objects.filter(offering=empty).count(), 2)
        self.assertEqual(Assessment.objects.filter(offering=empty).count(), 2)
        self.assertEqual(LOPOWeight.objects.filter(learning_outcome__offering=empty).count(), 3)
        self.assertEqual(AssessmentLOWeight.objects.filter(assessment__offering=empty).count(), 3)
        weight = AssessmentLOWeight.objects.get(
            assessment__offering=empty, learning_outcome__code="LO2", assessment__name="Midterm"
        )
        self.assertEqual(str(weight.weight), "0.50")

    def test_discard_writes_nothing(self):
        self.upload()
        before = self.counts()
        response = self.client.post(self.url("syllabus_discard"))
        self.assertRedirects(response, self.url("offering_setup"))
        self.assertEqual(self.counts(), before)
        self.assertNotIn(f"syllabus_proposal_{self.offering.id}", self.client.session)

    def test_llm_error_shows_message_and_writes_nothing(self):
        before = self.counts()
        with mock.patch("reporting.llm.generate_json", side_effect=llm.LLMError("Gemini request timed out.")):
            response = self.client.post(self.url("syllabus_upload"), {"text": "Course"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gemini request timed out.")
        self.assertEqual(self.counts(), before)
        self.assertNotIn(f"syllabus_proposal_{self.offering.id}", self.client.session)

    def test_invalid_reply_shows_error_and_writes_nothing(self):
        before = self.counts()
        response, _ = self.upload(reply={"learning_outcomes": [], "assessments": []})
        self.assertContains(response, "no usable")
        self.assertEqual(self.counts(), before)
        self.assertNotIn(f"syllabus_proposal_{self.offering.id}", self.client.session)

    def test_unreadable_file_and_bad_files(self):
        with mock.patch("reporting.llm.generate_json") as generate:
            for upload in (
                SimpleUploadedFile("a.pdf", b"not a pdf"),
                SimpleUploadedFile("a.txt", b"   "),
                SimpleUploadedFile("a.docx", b"x"),
                SimpleUploadedFile("big.txt", b"x" * (2 * 1024 * 1024 + 1)),
            ):
                response = self.client.post(self.url("syllabus_upload"), {"file": upload})
                self.assertEqual(response.status_code, 200)
        generate.assert_not_called()

    def test_file_upload_sends_file_text(self):
        upload = SimpleUploadedFile("syllabus.txt", b"Week 1: intro to databases")
        with mock.patch("reporting.llm.generate_json", return_value=good_reply()) as generate:
            response = self.client.post(self.url("syllabus_upload"), {"file": upload})
        self.assertRedirects(response, self.url("syllabus_review"))
        self.assertIn("Week 1: intro to databases", generate.call_args.args[0])

    def test_empty_form_is_rejected(self):
        with mock.patch("reporting.llm.generate_json") as generate:
            response = self.client.post(self.url("syllabus_upload"), {"text": "  "})
        generate.assert_not_called()
        self.assertContains(response, "Upload a file or paste")

    def test_model_text_is_escaped(self):
        reply = {"learning_outcomes": [{"code": "LO7", "description": "<script>alert(1)</script>"}]}
        self.upload(reply=reply)
        response = self.client.get(self.url("syllabus_review"))
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")

    def test_review_and_apply_without_proposal_redirect_to_upload(self):
        before = self.counts()
        self.assertRedirects(self.client.get(self.url("syllabus_review")), self.url("syllabus_upload"))
        self.assertRedirects(self.client.post(self.url("syllabus_apply")), self.url("syllabus_upload"))
        self.assertEqual(self.counts(), before)

    def test_apply_and_discard_need_post(self):
        self.assertEqual(self.client.get(self.url("syllabus_apply")).status_code, 405)
        self.assertEqual(self.client.get(self.url("syllabus_discard")).status_code, 405)


@override_settings(GEMINI_API_KEY="test-key")
class SyllabusPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        cls.offering = CourseOffering.objects.get(course__code="CSE311")
        cls.other = User.objects.create_user(username="other_instructor", password="x", role=User.Role.INSTRUCTOR)

    def urls(self):
        names = ["syllabus_upload", "syllabus_review", "syllabus_apply", "syllabus_discard"]
        return [reverse(f"curriculum:{name}", args=[self.offering.id]) for name in names]

    def test_student_gets_403_everywhere(self):
        self.client.force_login(User.objects.get(username="Batuhan"))
        for url in self.urls():
            self.assertEqual(self.client.get(url).status_code, 403, url)
            self.assertEqual(self.client.post(url, {"text": "x"}).status_code, 403, url)

    def test_other_instructor_gets_404_everywhere(self):
        self.client.force_login(self.other)
        for url in self.urls():
            self.assertEqual(self.client.get(url).status_code in (404, 405), True, url)
            self.assertEqual(self.client.post(url, {"text": "x"}).status_code, 404, url)

    def test_anonymous_is_sent_to_login(self):
        for url in self.urls():
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/accounts/login/", response.url)
