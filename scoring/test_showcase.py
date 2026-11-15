from django.core.management import call_command
from django.test import TestCase

from accounts.models import User
from alerts.models import POAlert
from alerts.services import sync_alerts
from curriculum.models import Course, CourseOffering, LOPOWeight
from grading.models import Enrollment, Grade
from reporting.rules import LOW_SCORE_THRESHOLD
from scoring.management.commands.seed_demo import TERM
from scoring.models import StudentLOScore, StudentPOScore

DEMO_LOGINS = ["Batuhan", "Ali"]


def counts():
    return {
        "users": User.objects.count(),
        "courses": Course.objects.count(),
        "offerings": CourseOffering.objects.count(),
        "enrollments": Enrollment.objects.count(),
        "grades": Grade.objects.count(),
        "lo_scores": StudentLOScore.objects.count(),
        "po_scores": StudentPOScore.objects.count(),
        "alerts": POAlert.objects.count(),
    }


def grade_table():
    return sorted(Grade.objects.values_list("enrollment__student__username", "assessment_id", "score"))


def po_scores(username, numbers):
    rows = StudentPOScore.objects.filter(student__username=username, program_outcome__number__in=numbers)
    return {row.program_outcome.number: row.score for row in rows}


class SeedShowcaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Seeding is slow (every grade feeds the score cache), so seed once for all tests in this class.
        call_command("seed_demo", verbosity=0)
        cls.plain_counts = counts()
        cls.plain_demo_scores = {name: po_scores(name, range(1, 6)) for name in DEMO_LOGINS}
        call_command("seed_showcase", verbosity=0)

    def test_idempotent(self):
        first, first_grades = counts(), grade_table()
        call_command("seed_showcase", verbosity=0)
        self.assertEqual(first, counts())
        self.assertEqual(first_grades, grade_table())

    def test_sizes(self):
        self.assertEqual(User.objects.filter(role=User.Role.STUDENT).count(), 26)
        self.assertEqual(CourseOffering.objects.filter(term=TERM).count(), 6)
        self.assertEqual(Enrollment.objects.count(), 26 * 6)

    def test_all_pos_are_covered(self):
        covered = set(
            LOPOWeight.objects.filter(learning_outcome__offering__term=TERM).values_list(
                "program_outcome__number", flat=True
            )
        )
        self.assertEqual(covered, set(range(1, 12)))

    def test_demo_students_keep_guideline_po1_to_po5(self):
        for name in DEMO_LOGINS:
            self.assertEqual(len(self.plain_demo_scores[name]), 5)
            self.assertEqual(self.plain_demo_scores[name], po_scores(name, range(1, 6)))
            self.assertEqual(StudentPOScore.objects.filter(student__username=name).count(), 11)

    def test_low_and_incomplete_scores_exist(self):
        low = StudentPOScore.objects.filter(score__lt=LOW_SCORE_THRESHOLD)
        self.assertGreaterEqual(low.values("student").distinct().count(), 4)
        self.assertFalse(low.filter(student__username__in=DEMO_LOGINS).exists())
        self.assertTrue(StudentPOScore.objects.filter(is_incomplete=True).exists())

    def test_alerts_are_created(self):
        self.assertGreater(sync_alerts()["created"], 0)

    def test_remove_restores_plain_seed_demo(self):
        sync_alerts()
        call_command("seed_showcase", "--remove", verbosity=0)
        self.assertEqual(self.plain_counts, counts())
        self.assertEqual(set(po_scores("Batuhan", range(1, 12))), {1, 2, 3, 4, 5})
