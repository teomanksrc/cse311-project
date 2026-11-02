"""View and permission tests, built on the seed_demo dataset."""

from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from curriculum.models import Assessment, Course, CourseOffering
from grading.models import Enrollment, Grade
from scoring.models import StudentPOScore


class ViewTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        cls.elif_ = User.objects.get(username="Batuhan")
        cls.can = User.objects.get(username="Ali")
        cls.instructor = User.objects.get(username="instructor")
        cls.cse311_midterm = Assessment.objects.get(offering__course__code="CSE311", name="Midterm")

    def login(self, username):
        self.client.force_login(User.objects.get(username=username))


class AccessControlTests(ViewTestBase):
    def test_anonymous_users_are_sent_to_login(self):
        for name, args in [
            ("scoring:student_dashboard", []),
            ("scoring:department_dashboard", []),
            ("grading:instructor_home", []),
            ("grading:enter_grades", [self.cse311_midterm.id]),
        ]:
            response = self.client.get(reverse(name, args=args))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn("/accounts/login/", response.url)

    def test_student_cannot_open_staff_pages(self):
        self.login("Batuhan")
        self.assertEqual(self.client.get(reverse("scoring:department_dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("grading:instructor_home")).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("grading:enter_grades", args=[self.cse311_midterm.id])).status_code, 403
        )

    def test_instructor_and_head_cannot_open_student_dashboard(self):
        for username in ("instructor", "head"):
            self.login(username)
            self.assertEqual(self.client.get(reverse("scoring:student_dashboard")).status_code, 403, username)

    def test_home_redirects_by_role(self):
        expected = {
            "Batuhan": "scoring:student_dashboard",
            "instructor": "grading:instructor_home",
            "head": "scoring:department_dashboard",
            "admin": "scoring:department_dashboard",
        }
        for username, target in expected.items():
            self.login(username)
            self.assertRedirects(self.client.get(reverse("home")), reverse(target), fetch_redirect_response=False)

    def test_only_admin_sees_admin_panel_link(self):
        admin_url = reverse("admin:index")
        self.login("admin")
        self.assertContains(self.client.get(reverse("scoring:department_dashboard")), f'href="{admin_url}"')
        for username in ("head", "instructor", "Batuhan"):
            self.login(username)
            response = self.client.get(reverse("home"), follow=True)
            self.assertNotContains(response, f'href="{admin_url}"', msg_prefix=username)

    def test_login_page_and_login_flow(self):
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 200)
        response = self.client.post(reverse("accounts:login"), {"username": "Batuhan", "password": "1234"})
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)


class StudentIsolationTests(ViewTestBase):
    """A student must never see another student's data."""

    def test_student_sees_only_own_scores_and_grades(self):
        self.login("Batuhan")
        response = self.client.get(reverse("scoring:student_dashboard"))
        self.assertEqual(response.status_code, 200)
        profile = {row["po"].number: row["score"] for row in response.context["profile"]}
        own = StudentPOScore.objects.get(student=self.elif_, program_outcome__number=1)
        other = StudentPOScore.objects.get(student=self.can, program_outcome__number=1)
        self.assertEqual(profile[1], float(round(own.score, 1)))
        self.assertNotEqual(profile[1], float(round(other.score, 1)))
        for course in response.context["courses"]:
            self.assertEqual(course["offering"].enrollments.filter(student=self.elif_).count(), 1)
            for grade in course["grades"]:
                self.assertEqual(grade.enrollment.student, self.elif_)

    def test_other_students_grades_do_not_appear_in_page(self):
        # Give Can a recognisable grade and make sure Elif's page does not contain it.
        enrollment = Enrollment.objects.get(student=self.can, offering__course__code="MAT241")
        Grade.objects.filter(enrollment=enrollment, assessment__name="Final").update(score=Decimal("77.77"))
        self.login("Batuhan")
        self.assertNotContains(self.client.get(reverse("scoring:student_dashboard")), "77.77")

    def test_dashboard_ignores_student_id_query_parameters(self):
        self.login("Batuhan")
        response = self.client.get(reverse("scoring:student_dashboard"), {"student": self.can.id, "user": self.can.id})
        profile = {row["po"].number: row["score"] for row in response.context["profile"]}
        own = StudentPOScore.objects.get(student=self.elif_, program_outcome__number=2)
        self.assertEqual(profile[2], float(round(own.score, 1)))


class GradeEntryTests(ViewTestBase):
    def url(self):
        return reverse("grading:enter_grades", args=[self.cse311_midterm.id])

    def field(self, student):
        enrollment = Enrollment.objects.get(student=student, offering=self.cse311_midterm.offering)
        return f"score_{enrollment.id}"

    def test_instructor_saves_grades_and_scores_are_recomputed(self):
        self.login("instructor")
        data = {self.field(self.elif_): "100", self.field(self.can): "50"}
        response = self.client.post(self.url(), data)
        self.assertRedirects(response, self.url(), fetch_redirect_response=False)
        grade = Grade.objects.get(enrollment__student=self.elif_, assessment=self.cse311_midterm)
        self.assertEqual(grade.score, Decimal("100"))
        po1 = StudentPOScore.objects.get(student=self.elif_, program_outcome__number=1)
        self.assertGreater(po1.score, Decimal("85"))  # was 85.0 with midterm 90

    def test_invalid_grade_saves_nothing(self):
        self.login("instructor")
        before = Grade.objects.filter(assessment=self.cse311_midterm).count()
        data = {self.field(self.elif_): "55", self.field(self.can): "101"}
        response = self.client.post(self.url(), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Must be between 0 and 100")
        self.assertEqual(Grade.objects.filter(assessment=self.cse311_midterm).count(), before)
        self.assertEqual(
            Grade.objects.get(enrollment__student=self.elif_, assessment=self.cse311_midterm).score, Decimal("90")
        )

    def test_non_numeric_grade_is_rejected(self):
        self.login("instructor")
        response = self.client.post(self.url(), {self.field(self.elif_): "abc", self.field(self.can): "80"})
        self.assertContains(response, "Not a number")

    def test_blank_grade_deletes_it_and_marks_incomplete(self):
        self.login("instructor")
        self.client.post(self.url(), {self.field(self.elif_): "", self.field(self.can): "100"})
        self.assertFalse(Grade.objects.filter(enrollment__student=self.elif_, assessment=self.cse311_midterm).exists())
        self.assertTrue(StudentPOScore.objects.get(student=self.elif_, program_outcome__number=1).is_incomplete)

    def test_instructor_cannot_edit_another_instructors_course(self):
        other = User.objects.create_user("other", password="x", role=User.Role.INSTRUCTOR)
        offering = CourseOffering.objects.create(
            course=Course.objects.create(code="XXX100", name="X"), term="2026-Fall", instructor=other
        )
        theirs = Assessment.objects.create(offering=offering, name="Quiz")
        self.login("instructor")
        self.assertEqual(self.client.get(reverse("grading:enter_grades", args=[theirs.id])).status_code, 404)
        self.assertEqual(self.client.post(reverse("grading:enter_grades", args=[theirs.id]), {}).status_code, 404)

    def test_instructor_home_lists_only_own_offerings(self):
        other = User.objects.create_user("other", password="x", role=User.Role.INSTRUCTOR)
        CourseOffering.objects.create(
            course=Course.objects.create(code="XXX100", name="X"), term="2026-Fall", instructor=other
        )
        self.login("instructor")
        response = self.client.get(reverse("grading:instructor_home"))
        codes = {o.course.code for o in response.context["offerings"]}
        self.assertEqual(codes, {"CSE311", "CSE321", "MAT241"})


class DepartmentDashboardTests(ViewTestBase):
    def test_head_sees_average_per_po(self):
        self.login("head")
        response = self.client.get(reverse("scoring:department_dashboard"))
        self.assertEqual(response.status_code, 200)
        rows = {r["po"].number: r for r in response.context["rows"]}
        scores = StudentPOScore.objects.filter(program_outcome__number=1).values_list("score", flat=True)
        expected = round(float(sum(scores) / len(scores)), 1)
        self.assertEqual(rows[1]["average"], expected)
        self.assertEqual(rows[1]["students"], 2)
        self.assertIsNone(rows[8]["average"])  # no course feeds PO8 in the demo data
        self.assertEqual(len(response.context["chart"]["labels"]), 11)

    def test_admin_can_open_it_too(self):
        self.login("admin")
        self.assertEqual(self.client.get(reverse("scoring:department_dashboard")).status_code, 200)
