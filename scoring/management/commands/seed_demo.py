"""Seed a complete demo dataset. Safe to run repeatedly (idempotent).

    python manage.py seed_demo

Demo logins (password for all: 1234):
    admin / head / instructor / Batuhan / Ali
"""

from decimal import Decimal

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

DEMO_PASSWORD = "1234"
TERM = "2026-Fall"

PROGRAM_OUTCOMES = {
    1: "Math, science & engineering knowledge",
    2: "Identify, formulate & solve engineering problems",
    3: "Design systems under realistic constraints",
    4: "Use modern techniques, tools & IT",
    5: "Design & run experiments, analyze data",
    6: "Work in teams and individually",
    7: "Communicate verbally & in writing",
    8: "Lifelong learning",
    9: "Ethics & professional responsibility",
    10: "Project, risk & change management; entrepreneurship",
    11: "Health, safety, environment & legal effects",
}

# CSE 311 reproduces the guideline's Elif example, with LO->PO weights 2:1 (same ratio as 1.0:0.5).
COURSES = {
    "CSE311": {
        "name": "Software Engineering",
        "assessments": ["Midterm", "Project"],
        "los": {"LO1": "Agile process and teamwork", "LO2": "Testing, CI/CD and delivery"},
        "assessment_weights": {
            ("Midterm", "LO1"): "0.6",
            ("Midterm", "LO2"): "0.4",
            ("Project", "LO1"): "0.4",
            ("Project", "LO2"): "1.0",
        },
        "po_weights": {("LO1", 1): 2, ("LO2", 1): 1, ("LO2", 2): 2},
    },
    "CSE321": {
        "name": "Data Systems",
        "assessments": ["Midterm", "Project"],
        "los": {"LO1": "Data modeling", "LO2": "Scalability and consistency"},
        "assessment_weights": {
            ("Midterm", "LO1"): "0.5",
            ("Midterm", "LO2"): "0.5",
            ("Project", "LO1"): "0.5",
            ("Project", "LO2"): "0.5",
        },
        "po_weights": {("LO1", 3): 4, ("LO1", 4): 3, ("LO2", 3): 3, ("LO2", 5): 4},
    },
    "MAT241": {
        "name": "Probability and Statistics",
        "assessments": ["Midterm", "Final"],
        "los": {"LO1": "Statistical analysis of data"},
        "assessment_weights": {("Midterm", "LO1"): "0.4", ("Final", "LO1"): "0.6"},
        "po_weights": {("LO1", 5): 3},
    },
}

STUDENTS = {
    "Batuhan": ("Batuhan", "Büyüknacar", "20260001"),
    "Ali": ("Ali Emre", "Sayan", "20260002"),
}

GRADES = {
    "Batuhan": {
        "CSE311": {"Midterm": 90, "Project": 80},
        "CSE321": {"Midterm": 88, "Project": 92},
        "MAT241": {"Midterm": 75, "Final": 80},
    },
    "Ali": {
        "CSE311": {"Midterm": 100, "Project": 90},
        "CSE321": {"Midterm": 95, "Project": 85},
        "MAT241": {"Midterm": 90, "Final": 95},
    },
}


def upsert_user(username, role, first_name, last_name, student_number=None):
    user, _ = User.objects.get_or_create(username=username)
    user.role = role
    user.first_name, user.last_name = first_name, last_name
    user.student_number = student_number
    user.email = f"{username}@example.com"
    user.is_staff = role == User.Role.ADMIN
    user.is_superuser = role == User.Role.ADMIN
    user.set_password(DEMO_PASSWORD)
    user.save()
    return user


class Command(BaseCommand):
    help = "Create demo data: POs, courses, weights, users and grades (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        upsert_user("admin", User.Role.ADMIN, "System", "Admin")
        upsert_user("head", User.Role.HEAD, "Head", "Of Department")
        instructor = upsert_user("instructor", User.Role.INSTRUCTOR, "Ahmet", "Instructor")
        students = {
            username: upsert_user(username, User.Role.STUDENT, first, last, number)
            for username, (first, last, number) in STUDENTS.items()
        }

        pos = {}
        for number, short_name in PROGRAM_OUTCOMES.items():
            pos[number], _ = ProgramOutcome.objects.update_or_create(number=number, defaults={"short_name": short_name})

        offerings = {}
        for code, spec in COURSES.items():
            course, _ = Course.objects.update_or_create(code=code, defaults={"name": spec["name"]})
            offering, _ = CourseOffering.objects.update_or_create(
                course=course, term=TERM, defaults={"instructor": instructor}
            )
            offerings[code] = offering
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

        for username, student in students.items():
            for code, grades in GRADES[username].items():
                enrollment, _ = Enrollment.objects.get_or_create(student=student, offering=offerings[code])
                for assessment_name, score in grades.items():
                    Grade.objects.update_or_create(
                        enrollment=enrollment,
                        assessment=Assessment.objects.get(offering=offerings[code], name=assessment_name),
                        defaults={"score": score},
                    )

        if options["verbosity"] > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Demo data ready. Log in with any of admin/head/instructor/Batuhan/Ali, password: {DEMO_PASSWORD}"
                )
            )
