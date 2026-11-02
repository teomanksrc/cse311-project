from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from accounts.models import User
from curriculum.models import ProgramOutcome
from grading.models import Grade
from scoring.models import StudentPOScore


def snapshot():
    return {
        "users": User.objects.count(),
        "pos": ProgramOutcome.objects.count(),
        "grades": Grade.objects.count(),
        "po_scores": StudentPOScore.objects.count(),
    }


class SeedDemoTests(TestCase):
    def test_seed_is_idempotent(self):
        call_command("seed_demo", verbosity=0)
        first = snapshot()
        call_command("seed_demo", verbosity=0)
        self.assertEqual(first, snapshot())
        self.assertEqual(first["pos"], 11)
        self.assertEqual(first["users"], 5)

    def test_elif_cse311_example_with_2_to_1_weights(self):
        call_command("seed_demo", verbosity=0)
        elif_ = User.objects.get(username="Batuhan")
        # PO1 is fed only by CSE311, PO2 only by CSE311 as well.
        po1 = StudentPOScore.objects.get(student=elif_, program_outcome__number=1)
        po2 = StudentPOScore.objects.get(student=elif_, program_outcome__number=2)
        self.assertEqual(round(po1.score, 1), Decimal("85.0"))
        self.assertEqual(round(po2.score, 1), Decimal("82.9"))

    def test_po5_aggregates_two_courses(self):
        call_command("seed_demo", verbosity=0)
        elif_ = User.objects.get(username="Batuhan")
        po5 = StudentPOScore.objects.get(student=elif_, program_outcome__number=5)
        # CSE321 LO2 = 90 (weight 4), MAT241 LO1 = 78 (weight 3)
        self.assertEqual(round(po5.score, 1), round((Decimal("90") * 4 + Decimal("78") * 3) / 7, 1))
