"""Add a larger, deterministic showcase dataset on top of seed_demo (idempotent).

    python manage.py seed_showcase             # seed_demo + 3 extra courses + 24 more students
    python manage.py seed_showcase --remove    # delete only what the showcase added

The extra courses feed PO6-PO11 only, so Batuhan's and Ali's PO1-PO5 scores keep the
guideline values from seed_demo. Every student here logs in with the demo password (1234).
"""

import random
from decimal import Decimal

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

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
from scoring.management.commands.seed_demo import COURSES as DEMO_COURSES
from scoring.management.commands.seed_demo import DEMO_PASSWORD, TERM, upsert_user
from scoring.recompute import recompute_student
from scoring.stats import refresh_department_stats

RANDOM_SEED = 311  # fixed, so every run produces the same grades

# Same shape as COURSES in seed_demo. LO->PO links only use PO6-PO11 (see the module docstring).
SHOWCASE_COURSES = {
    "CSE491": {
        "name": "Senior Design Project",
        "assessments": ["Proposal", "Demo", "Report"],
        "los": {"LO1": "Team work and project planning", "LO2": "Technical reporting"},
        "assessment_weights": {
            ("Proposal", "LO1"): "0.5",
            ("Demo", "LO1"): "0.8",
            ("Demo", "LO2"): "0.3",
            ("Report", "LO2"): "1.0",
        },
        "po_weights": {("LO1", 6): 4, ("LO1", 10): 3, ("LO2", 7): 4, ("LO2", 8): 2},
    },
    "CSE403": {
        "name": "Professional Ethics and Law",
        "assessments": ["Midterm", "Case Study"],
        "los": {"LO1": "Ethical responsibility", "LO2": "Legal, safety and environmental effects"},
        "assessment_weights": {
            ("Midterm", "LO1"): "0.6",
            ("Midterm", "LO2"): "0.4",
            ("Case Study", "LO1"): "0.4",
            ("Case Study", "LO2"): "0.6",
        },
        "po_weights": {("LO1", 9): 5, ("LO2", 11): 4, ("LO2", 9): 2},
    },
    "ENG301": {
        "name": "Technical Communication",
        "assessments": ["Presentation", "Essay", "Final"],
        "los": {"LO1": "Present and write for technical audiences", "LO2": "Manage change and keep learning"},
        "assessment_weights": {
            ("Presentation", "LO1"): "0.6",
            ("Essay", "LO1"): "0.4",
            ("Essay", "LO2"): "0.5",
            ("Final", "LO2"): "0.8",
        },
        "po_weights": {("LO1", 7): 3, ("LO1", 6): 2, ("LO2", 8): 4, ("LO2", 10): 3},
    },
}

# username: (first name, last name, base level). The base level is the centre of that student's grades.
# Batuhan and Ali are not here: their grades are written out in DEMO_STUDENT_GRADES.
SHOWCASE_STUDENTS = {
    "ayse": ("Ayşe", "Yılmaz", 88),
    "mehmet": ("Mehmet", "Kaya", 76),
    "fatma": ("Fatma", "Demir", 92),
    "mustafa": ("Mustafa", "Çelik", 42),  # clearly weak: most POs end up below 60
    "zeynep": ("Zeynep", "Şahin", 81),
    "emre": ("Emre", "Yıldız", 54),  # weak
    "elif": ("Elif", "Öztürk", 85),
    "can": ("Can", "Aydın", 70),
    "selin": ("Selin", "Arslan", 78),  # fails only the ethics course (see COURSE_DIPS)
    "burak": ("Burak", "Doğan", 80),  # struggles only in the senior project (see COURSE_DIPS)
    "deniz": ("Deniz", "Kılıç", 73),
    "merve": ("Merve", "Aslan", 90),
    "kerem": ("Kerem", "Çetin", 66),
    "ece": ("Ece", "Kara", 84),
    "oguz": ("Oğuz", "Koç", 62),
    "gizem": ("Gizem", "Kurt", 77),
    "tolga": ("Tolga", "Özkan", 69),
    "buse": ("Buse", "Şimşek", 94),
    "yusuf": ("Yusuf", "Polat", 74),
    "irem": ("İrem", "Erdoğan", 87),
    "onur": ("Onur", "Güneş", 64),
    "dilara": ("Dilara", "Aksoy", 79),
    "cem": ("Cem", "Tekin", 72),
    "hande": ("Hande", "Bulut", 83),
}

# A student who is fine overall but does badly in one course: (username, course code) -> base level.
COURSE_DIPS = {("selin", "CSE403"): 38, ("burak", "CSE491"): 42}

# Grades that were never entered (no Grade row), so the "incomplete" flag is visible: (username, course, assessment).
MISSING_GRADES = {("zeynep", "CSE491", "Report"), ("can", "CSE403", "Case Study"), ("irem", "ENG301", "Final")}

# The two well-known demo logins stay "clean": good grades (>= 70) in the new courses.
DEMO_STUDENT_GRADES = {
    "Batuhan": {
        "CSE491": {"Proposal": 85, "Demo": 90, "Report": 82},
        "CSE403": {"Midterm": 78, "Case Study": 88},
        "ENG301": {"Presentation": 92, "Essay": 84, "Final": 80},
    },
    "Ali": {
        "CSE491": {"Proposal": 95, "Demo": 92, "Report": 90},
        "CSE403": {"Midterm": 85, "Case Study": 91},
        "ENG301": {"Presentation": 88, "Essay": 93, "Final": 86},
    },
}

FIRST_STUDENT_NUMBER = 20260003
ALL_COURSES = {**DEMO_COURSES, **SHOWCASE_COURSES}  # the showcase students take all six


def clamp(score):
    return max(0, min(100, score))


def build_grades():
    """Return {username: {course code: {assessment: score}}} for the 24 showcase students.

    Each grade is the student's base level (or course dip) plus a small deterministic random offset.
    """
    rng = random.Random(RANDOM_SEED)
    result = {}
    for username, (_first, _last, base) in SHOWCASE_STUDENTS.items():
        result[username] = {}
        for code, spec in ALL_COURSES.items():
            level = COURSE_DIPS.get((username, code), base)
            result[username][code] = {
                name: clamp(level + rng.randint(-7, 7))
                for name in spec["assessments"]
                if (username, code, name) not in MISSING_GRADES
            }
    for username, courses in DEMO_STUDENT_GRADES.items():
        result[username] = courses  # only the three new courses; seed_demo owns the other grades
    return result


class Command(BaseCommand):
    help = "Add a larger showcase dataset on top of seed_demo (idempotent). Use --remove to undo it."

    def add_arguments(self, parser):
        parser.add_argument("--remove", action="store_true", help="Delete the showcase students and courses")

    def handle(self, *args, **options):
        if options["remove"]:
            self.remove()
        else:
            # The base data (POs, instructor, Batuhan, Ali) must exist first.
            call_command("seed_demo", verbosity=options["verbosity"])
            self.seed()
        refresh_department_stats()  # after the commit, see scoring/stats.py
        if options["verbosity"] > 0:
            students = User.objects.filter(role=User.Role.STUDENT).count()
            courses = Course.objects.count()
            if options["remove"]:
                message = f"Showcase data removed. {students} students and {courses} courses remain (plain seed_demo)."
            else:
                message = (
                    f"Showcase data ready: {students} students, {courses} courses. "
                    f"Every login uses the demo password: {DEMO_PASSWORD}"
                )
            self.stdout.write(self.style.SUCCESS(message))

    @transaction.atomic
    def seed(self):
        instructor = User.objects.get(username="instructor")
        pos = {po.number: po for po in ProgramOutcome.objects.all()}

        offerings = {code: CourseOffering.objects.get(course__code=code, term=TERM) for code in DEMO_COURSES}
        for code, spec in SHOWCASE_COURSES.items():
            offerings[code] = self.seed_course(code, spec, instructor, pos)

        students = {username: User.objects.get(username=username) for username in DEMO_STUDENT_GRADES}
        for number, (username, (first, last, _base)) in enumerate(
            SHOWCASE_STUDENTS.items(), start=FIRST_STUDENT_NUMBER
        ):
            students[username] = upsert_user(username, User.Role.STUDENT, first, last, str(number))

        # Bulk writes send no signals, so the cached scores are recomputed once per student afterwards.
        # (Saving ~400 grades one by one would recompute the same student hundreds of times.)
        grades = build_grades()
        Enrollment.objects.bulk_create(
            [
                Enrollment(student=student, offering=offering)
                for username, student in students.items()
                for code, offering in offerings.items()
                if not (username in DEMO_STUDENT_GRADES and code in DEMO_COURSES)  # seed_demo owns those
            ],
            ignore_conflicts=True,
        )
        enrollments = {
            (e.student_id, e.offering_id): e for e in Enrollment.objects.filter(student__in=students.values())
        }
        assessments = {
            (a.offering.course.code, a.name): a
            for a in Assessment.objects.filter(offering__in=offerings.values()).select_related("offering__course")
        }
        rows = [
            Grade(
                enrollment=enrollments[(student.id, offerings[code].id)],
                assessment=assessments[(code, name)],
                score=score,
            )
            for username, student in students.items()
            for code, course_grades in grades[username].items()
            for name, score in course_grades.items()
        ]
        Grade.objects.bulk_create(
            rows, update_conflicts=True, unique_fields=["enrollment", "assessment"], update_fields=["score"]
        )
        for student in sorted(students.values(), key=lambda user: user.id):  # id order, as recompute.py requires
            recompute_student(student)

    def seed_course(self, code, spec, instructor, pos):
        course, _ = Course.objects.update_or_create(code=code, defaults={"name": spec["name"]})
        offering, _ = CourseOffering.objects.update_or_create(
            course=course, term=TERM, defaults={"instructor": instructor}
        )
        los = {
            lo_code: LearningOutcome.objects.update_or_create(
                offering=offering, code=lo_code, defaults={"description": text}
            )[0]
            for lo_code, text in spec["los"].items()
        }
        assessments = {
            name: Assessment.objects.get_or_create(offering=offering, name=name)[0] for name in spec["assessments"]
        }
        for (assessment_name, lo_code), weight in spec["assessment_weights"].items():
            AssessmentLOWeight.objects.update_or_create(
                assessment=assessments[assessment_name],
                learning_outcome=los[lo_code],
                defaults={"weight": Decimal(weight)},
            )
        for (lo_code, po_number), weight in spec["po_weights"].items():
            LOPOWeight.objects.update_or_create(
                learning_outcome=los[lo_code], program_outcome=pos[po_number], defaults={"weight": weight}
            )
        return offering

    @transaction.atomic
    def remove(self):
        # Deleting a user cascades to enrollments, grades, cached scores and alerts.
        User.objects.filter(username__in=SHOWCASE_STUDENTS).delete()
        # Deleting a course cascades to offerings, LOs, assessments, weights and ALL enrollments in them,
        # which includes Batuhan's and Ali's.
        Course.objects.filter(code__in=SHOWCASE_COURSES).delete()
        # Their cached PO6-PO11 rows must go too: recompute the two remaining demo students explicitly.
        for student in User.objects.filter(username__in=DEMO_STUDENT_GRADES).order_by("id"):
            recompute_student(student)
