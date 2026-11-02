"""PostgreSQL-specific consistency tests: row locking and index hygiene."""

from unittest import skipUnless

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from scoring.recompute import recompute_student

IS_POSTGRES = connection.vendor == "postgresql"


@skipUnless(IS_POSTGRES, "SELECT ... FOR UPDATE and pg_index only exist on PostgreSQL")
class PostgresConsistencyTests(TestCase):
    def test_recompute_locks_the_student_row_first(self):
        student = User.objects.create_user("locked", role=User.Role.STUDENT)
        with CaptureQueriesContext(connection) as ctx:
            recompute_student(student)
        selects = [q["sql"] for q in ctx.captured_queries if q["sql"].lstrip().upper().startswith("SELECT")]
        self.assertIn("FOR UPDATE", selects[0])
        self.assertIn('"accounts_user"', selects[0])

    def test_no_duplicate_indexes(self):
        """Two indexes on the same table, columns and operator classes are pure overhead."""
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT i.indrelid::regclass::text, array_agg(c.relname::text ORDER BY c.relname)
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = current_schema()
                GROUP BY i.indrelid, i.indkey::text, i.indclass::text, coalesce(i.indpred::text, '')
                HAVING count(*) > 1
                """
            )
            duplicates = cur.fetchall()
        self.assertEqual(duplicates, [])
