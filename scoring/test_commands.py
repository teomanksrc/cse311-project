"""Management commands: seed_load, db_stats, backup_db, restore_db. Docker is never called here."""

import subprocess
import tempfile
from io import StringIO
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.db import connection
from django.test import TestCase

from accounts.models import User
from curriculum.models import AssessmentLOWeight, CourseOffering, LearningOutcome, ProgramOutcome
from grading.models import Enrollment, Grade
from scoring.models import DepartmentPOStat, StudentLOScore, StudentPOScore
from scoring.recompute import recompute_student

TINY = ["--students", "12", "--offerings", "4", "--terms", "2", "--per-student", "2"]
IS_POSTGRES = connection.vendor == "postgresql"


def load(*args):
    out = StringIO()
    call_command("seed_load", *args, stdout=out)
    return out.getvalue()


class SeedLoadTests(TestCase):
    def test_creates_consistent_data(self):
        load(*TINY)
        self.assertEqual(User.objects.filter(role=User.Role.STUDENT).count(), 12)
        self.assertEqual(CourseOffering.objects.count(), 4)
        self.assertEqual(CourseOffering.objects.values("term").distinct().count(), 2)
        self.assertEqual(LearningOutcome.objects.count(), 16)
        self.assertEqual(ProgramOutcome.objects.count(), 11)
        self.assertEqual(Enrollment.objects.count(), 24)
        # every grade belongs to an assessment of the enrolled offering
        for grade in Grade.objects.select_related("enrollment", "assessment"):
            self.assertEqual(grade.enrollment.offering_id, grade.assessment.offering_id)
        self.assertGreater(AssessmentLOWeight.objects.count(), 0)
        self.assertGreater(StudentLOScore.objects.count(), 0)
        self.assertGreater(StudentPOScore.objects.count(), 0)
        self.assertEqual(DepartmentPOStat.objects.count(), 11)

    def test_cached_scores_match_a_fresh_recompute(self):
        load(*TINY)
        before = {(s.student_id, s.program_outcome_id): s.score for s in StudentPOScore.objects.all()}
        for student in User.objects.filter(role=User.Role.STUDENT):
            recompute_student(student)
        after = {(s.student_id, s.program_outcome_id): s.score for s in StudentPOScore.objects.all()}
        self.assertEqual(before, after)

    def test_is_deterministic(self):
        load(*TINY)
        first = list(
            Grade.objects.order_by("enrollment__student__username", "assessment_id").values_list("score", flat=True)
        )
        Grade.objects.all().delete()
        Enrollment.objects.all().delete()
        User.objects.filter(role=User.Role.STUDENT).delete()
        CourseOffering.objects.all().delete()
        load(*TINY, "--force")
        second = list(
            Grade.objects.order_by("enrollment__student__username", "assessment_id").values_list("score", flat=True)
        )
        self.assertEqual(first, second)

    def test_refuses_on_non_empty_database_without_force(self):
        User.objects.create_user("someone", role=User.Role.STUDENT)
        with self.assertRaisesMessage(CommandError, "--force"):
            load(*TINY)
        self.assertEqual(Grade.objects.count(), 0)

    def test_force_loads_anyway(self):
        User.objects.create_user("someone", role=User.Role.STUDENT)
        load(*TINY, "--force")
        self.assertEqual(User.objects.filter(role=User.Role.STUDENT).count(), 13)


class DbStatsTests(TestCase):
    def test_lists_application_tables(self):
        out = StringIO()
        call_command("db_stats", stdout=out)
        text = out.getvalue()
        for table in ("grading_grade", "scoring_studentposcore", "curriculum_courseoffering"):
            self.assertIn(table, text)
        self.assertNotIn("scoring_department_po_stats", text)  # a view has no storage
        if IS_POSTGRES:
            self.assertIn("total_size", text)


class BackupRestoreTests(TestCase):
    def test_restore_refuses_without_yes(self):
        with patch("subprocess.run") as run:
            with self.assertRaisesMessage(CommandError, "--yes"):
                call_command("restore_db", "whatever.dump")
        run.assert_not_called()

    @skipUnless(IS_POSTGRES, "backup and restore are PostgreSQL features")
    def test_restore_rejects_missing_file(self):
        with self.assertRaisesMessage(CommandError, "File not found"):
            call_command("restore_db", "does-not-exist.dump", "--yes")

    @skipUnless(IS_POSTGRES, "backup and restore are PostgreSQL features")
    def test_restore_runs_pg_restore_in_the_container(self):
        with tempfile.TemporaryDirectory() as folder, patch("subprocess.run") as run:
            dump = Path(folder) / "x.dump"
            dump.write_bytes(b"fake")
            run.return_value = subprocess.CompletedProcess([], 0, stderr=b"")
            call_command("restore_db", str(dump), "--yes", stdout=StringIO())
        command = run.call_args.args[0]
        self.assertEqual(command[:5], ["docker", "compose", "exec", "-T", "db"])
        self.assertIn("pg_restore", command)

    @skipUnless(IS_POSTGRES, "backup and restore are PostgreSQL features")
    def test_backup_writes_file_and_prints_path(self):
        with tempfile.TemporaryDirectory() as folder:

            def fake_dump(command, stdout, **kwargs):
                stdout.write(b"fake dump")
                return subprocess.CompletedProcess(command, 0, stderr=b"")

            out = StringIO()
            with patch("scoring.management.commands.backup_db.BACKUP_DIR", Path(folder)):
                with patch("subprocess.run", side_effect=fake_dump) as run:
                    call_command("backup_db", stdout=out)
                files = list(Path(folder).glob("*.dump"))
            self.assertEqual(len(files), 1)
            self.assertIn("pg_dump", run.call_args.args[0])
            self.assertIn(str(files[0]), out.getvalue())

    @skipUnless(IS_POSTGRES, "backup and restore are PostgreSQL features")
    def test_backup_failure_leaves_no_file(self):
        with tempfile.TemporaryDirectory() as folder:
            failed = subprocess.CompletedProcess([], 1, stderr=b"no such service")
            with patch("scoring.management.commands.backup_db.BACKUP_DIR", Path(folder)):
                with patch("subprocess.run", return_value=failed):
                    with self.assertRaisesMessage(CommandError, "no such service"):
                        call_command("backup_db")
                self.assertEqual(list(Path(folder).iterdir()), [])
                with patch("subprocess.run", side_effect=FileNotFoundError):
                    with self.assertRaisesMessage(CommandError, "Docker"):
                        call_command("backup_db")
                self.assertEqual(list(Path(folder).iterdir()), [])
