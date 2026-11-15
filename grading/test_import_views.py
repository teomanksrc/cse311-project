from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from accounts.models import User
from curriculum.models import CourseOffering
from grading.models import Grade
from scoring.models import StudentPOScore


class ImportViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        cls.offering = CourseOffering.objects.get(course__code="CSE311")
        cls.url = reverse("grading:import_grades", args=[cls.offering.id])
        cls.batuhan = User.objects.get(username="Batuhan")

    def login(self, username="instructor"):
        self.client.force_login(User.objects.get(username=username))

    def upload(self, name, content):
        return self.client.post(self.url, {"file": SimpleUploadedFile(name, content)})

    def grade(self, assessment_name):
        return Grade.objects.get(
            enrollment__student=self.batuhan, assessment__offering=self.offering, assessment__name=assessment_name
        )

    def po1(self):
        return StudentPOScore.objects.get(student=self.batuhan, program_outcome__number=1).score

    def test_permissions(self):
        for username in ("Batuhan", "head"):
            self.login(username)
            self.assertEqual(self.client.get(self.url).status_code, 403)
        other = User.objects.create_user("other", password="x", role=User.Role.INSTRUCTOR)
        self.client.force_login(other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url).status_code, 404)
        template_url = reverse("grading:import_template", args=[self.offering.id])
        self.assertEqual(self.client.get(template_url).status_code, 404)

    def test_csv_import_updates_grades_and_po_scores(self):
        self.login()
        before = self.po1()
        content = "﻿student_number;Midterm;Project\n20260001;50;\n20260002;;95,5\n".encode("utf-8")
        response = self.upload("grades.csv", content)
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.assertEqual(self.grade("Midterm").score, Decimal("50"))
        self.assertEqual(self.grade("Project").score, Decimal("80"))  # blank cell left it alone
        self.assertLess(self.po1(), before)
        page = self.client.get(self.url)
        self.assertContains(page, "0 grade(s) created, 2 updated")

    def test_xlsx_import(self):
        self.login()
        book = Workbook()
        book.active.append(["student_number", "Midterm"])
        book.active.append([20260001, 61])
        buffer = BytesIO()
        book.save(buffer)
        self.upload("grades.xlsx", buffer.getvalue())
        self.assertEqual(self.grade("Midterm").score, Decimal("61"))

    def test_import_creates_missing_grade(self):
        self.login()
        Grade.objects.filter(enrollment__student=self.batuhan, assessment__offering=self.offering).delete()
        self.upload("g.csv", b"student_number,Midterm\n20260001,70\n")
        self.assertEqual(self.grade("Midterm").score, Decimal("70"))

    def test_invalid_file_changes_nothing(self):
        self.login()
        before = list(Grade.objects.order_by("id").values_list("id", "score"))
        po_before = self.po1()
        response = self.upload("g.csv", b"student_number,Midterm,Nope\n20260001,50,1\n20260002,abc,\n99,1,\n")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "unknown assessment column")
        self.assertContains(response, "Row 3")
        self.assertContains(response, "Row 4")
        self.assertEqual(list(Grade.objects.order_by("id").values_list("id", "score")), before)
        self.assertEqual(self.po1(), po_before)

    def test_unreadable_missing_and_oversized_files(self):
        self.login()
        self.assertContains(self.upload("g.xlsx", b"junk"), "could not be read")
        self.assertContains(self.upload("g.csv", b"x" * (1024 * 1024 + 1)), "too large")
        self.assertContains(self.client.post(self.url), "Choose a file")

    def test_template_download(self):
        self.login()
        response = self.client.get(reverse("grading:import_template", args=[self.offering.id]))
        rows = list(load_workbook(BytesIO(response.content)).active.iter_rows(values_only=True))
        self.assertEqual(rows[0], ("student_number", "Midterm", "Project"))
        self.assertEqual(sorted(row[0] for row in rows[1:]), ["20260001", "20260002"])

    def test_filled_in_template_can_be_imported(self):
        """Download the template, type grades into it like an instructor would, upload it again."""
        self.login()
        response = self.client.get(reverse("grading:import_template", args=[self.offering.id]))
        workbook = load_workbook(BytesIO(response.content))
        sheet = workbook.active
        for row in sheet.iter_rows(min_row=2):
            row[1].value = 55
            row[2].value = 65
        buffer = BytesIO()
        workbook.save(buffer)
        upload = SimpleUploadedFile("grades.xlsx", buffer.getvalue())
        response = self.client.post(self.url, {"file": upload}, follow=True)
        self.assertContains(response, "Import finished")
        scores = set(Grade.objects.filter(assessment__offering=self.offering).values_list("score", flat=True))
        self.assertEqual(scores, {Decimal("55"), Decimal("65")})
