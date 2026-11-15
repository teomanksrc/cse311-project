"""Fill an EMPTY database with a larger, deterministic dataset for performance measurements.

    python manage.py seed_load                      # ~2,000 students, 40 offerings
    python manage.py seed_load --students 50 --offerings 4 --terms 2 --per-student 2

Never run it against the demo database. Rows are inserted with bulk_create (fast, sends no
signals), then recompute_student runs once per student to fill the cached score tables.
"""

import math
import random
import time
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError

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
from scoring.management.commands.seed_demo import PROGRAM_OUTCOMES
from scoring.recompute import recompute_student
from scoring.stats import refresh_department_stats

BATCH = 5000
MISSING_GRADE_RATE = 0.05  # some grades are not entered yet, like in real life


def term_name(index):
    """Term 0 = 2022-Fall, 1 = 2022-Spring, 2 = 2023-Fall, ..."""
    season = "Fall" if index % 2 == 0 else "Spring"
    return f"{2022 + index // 2}-{season}"


class Command(BaseCommand):
    help = "Bulk-load a large deterministic dataset (refuses if students already exist, unless --force)."

    def add_arguments(self, parser):
        parser.add_argument("--students", type=int, default=2000)
        parser.add_argument("--offerings", type=int, default=40)
        parser.add_argument("--terms", type=int, default=4, help="Offerings are spread over this many terms")
        parser.add_argument("--per-student", type=int, default=10, help="Enrollments per student")
        parser.add_argument("--los", type=int, default=4, help="Learning outcomes per offering")
        parser.add_argument("--assessments", type=int, default=4, help="Assessments per offering")
        parser.add_argument("--seed", type=int, default=42, help="Random seed (same seed = same data)")
        parser.add_argument("--force", action="store_true", help="Run even if students already exist")

    def log(self, text):
        self.stdout.write(f"[{time.time() - self.t0:7.1f}s] {text}")

    def handle(self, *args, **o):
        if User.objects.filter(role=User.Role.STUDENT).exists() and not o["force"]:
            raise CommandError("The database already contains students. Use --force to load anyway.")
        if o["terms"] < 1 or o["offerings"] < o["terms"]:
            raise CommandError("Need at least one offering per term.")
        per_student = min(o["per_student"], o["offerings"])
        rng = random.Random(o["seed"])
        self.t0 = time.time()

        pos = self.make_pos()
        offerings = self.make_curriculum(o, rng, pos)
        students = self.make_students(o["students"])
        self.log(f"{len(offerings)} offerings, {len(students)} students created")

        self.make_enrollments_and_grades(students, offerings, per_student, rng)

        self.log("recomputing scores (one recompute per student)...")
        for i, student_id in enumerate(students, start=1):
            recompute_student(User(pk=student_id))
            if i % 200 == 0 or i == len(students):
                self.log(f"  {i}/{len(students)} students recomputed")
        refresh_department_stats()
        self.stdout.write(self.style.SUCCESS(f"Done in {time.time() - self.t0:.1f}s"))

    def make_pos(self):
        for number, name in PROGRAM_OUTCOMES.items():
            ProgramOutcome.objects.get_or_create(number=number, defaults={"short_name": name})
        return list(ProgramOutcome.objects.order_by("number"))

    def make_curriculum(self, o, rng, pos):
        password = make_password("1234")  # hashing is slow, so hash once and reuse
        User.objects.bulk_create(
            [
                User(username=f"load_instr{i}", role=User.Role.INSTRUCTOR, password=password, first_name="Instr")
                for i in range(5)
            ],
            ignore_conflicts=True,
        )
        instructors = list(User.objects.filter(username__startswith="load_instr").order_by("id"))
        n_courses = math.ceil(o["offerings"] / o["terms"])
        Course.objects.bulk_create(
            [Course(code=f"LOAD{100 + i}", name=f"Load course {i}") for i in range(n_courses)], ignore_conflicts=True
        )
        courses = list(Course.objects.filter(code__startswith="LOAD").order_by("code"))
        # Offering i = course (i % n_courses) in term (i // n_courses): every (course, term) pair is unique.
        CourseOffering.objects.bulk_create(
            [
                CourseOffering(
                    course=courses[i % n_courses],
                    term=term_name(i // n_courses),
                    instructor=instructors[i % len(instructors)],
                )
                for i in range(o["offerings"])
            ],
            ignore_conflicts=True,
        )
        offerings = list(CourseOffering.objects.filter(course__in=courses).order_by("id"))
        LearningOutcome.objects.bulk_create(
            [LearningOutcome(offering=off, code=f"LO{n}") for off in offerings for n in range(1, o["los"] + 1)]
        )
        Assessment.objects.bulk_create(
            [Assessment(offering=off, name=f"A{n}") for off in offerings for n in range(1, o["assessments"] + 1)]
        )
        los = {}
        for lo in LearningOutcome.objects.filter(offering__in=offerings).order_by("id"):
            los.setdefault(lo.offering_id, []).append(lo)
        self.assessments_by_offering = {}
        for a in Assessment.objects.filter(offering__in=offerings).order_by("id"):
            self.assessments_by_offering.setdefault(a.offering_id, []).append(a)

        links, po_links = [], []
        for off in offerings:
            off_los = los[off.id]
            for n, assessment in enumerate(self.assessments_by_offering[off.id]):
                for lo in {off_los[n % len(off_los)], off_los[(n + 1) % len(off_los)]}:  # up to 2 LOs each
                    weight = Decimal(rng.randint(2, 10)) / 10
                    links.append(AssessmentLOWeight(assessment=assessment, learning_outcome=lo, weight=weight))
            for lo in off_los:
                for po in rng.sample(pos, 2):  # each LO feeds 2 POs
                    po_links.append(LOPOWeight(learning_outcome=lo, program_outcome=po, weight=rng.randint(1, 5)))
        AssessmentLOWeight.objects.bulk_create(links, batch_size=BATCH)
        LOPOWeight.objects.bulk_create(po_links, batch_size=BATCH)
        return offerings

    def make_students(self, count):
        password = make_password("1234")
        User.objects.bulk_create(
            [
                User(
                    username=f"load{i:05d}",
                    role=User.Role.STUDENT,
                    password=password,
                    student_number=f"L{i:07d}",
                    first_name=f"Student{i}",
                    last_name="Load",
                )
                for i in range(count)
            ],
            batch_size=BATCH,
        )
        return list(User.objects.filter(username__regex=r"^load\d{5}$").order_by("id").values_list("id", flat=True))

    def make_enrollments_and_grades(self, students, offerings, per_student, rng):
        Enrollment.objects.bulk_create(
            [
                Enrollment(student_id=student_id, offering=off)
                for student_id in students
                for off in rng.sample(offerings, per_student)
            ],
            batch_size=BATCH,
        )
        self.log("enrollments created")
        grades = []
        for enrollment in Enrollment.objects.filter(student_id__in=students).order_by("id").iterator():
            for assessment in self.assessments_by_offering[enrollment.offering_id]:
                if rng.random() >= MISSING_GRADE_RATE:
                    score = Decimal(rng.randint(300, 1000)) / 10
                    grades.append(Grade(enrollment=enrollment, assessment=assessment, score=score))
        Grade.objects.bulk_create(grades, batch_size=BATCH)
        self.log(f"{len(grades)} grades created")
