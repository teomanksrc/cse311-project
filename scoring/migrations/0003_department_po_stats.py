# Creates the department averages view. Written with Django's help, then edited by hand (RunPython).

import django.db.models.deletion
from django.db import migrations, models


# Same SELECT on both databases. LEFT JOIN keeps POs that have no scores yet.
# SUM(CASE ...) instead of COUNT(...) FILTER so that SQLite runs it unchanged.
SELECT_SQL = """
    SELECT po.id AS program_outcome_id,
           AVG(s.score) AS average,
           COUNT(s.id) AS students,
           COALESCE(SUM(CASE WHEN s.is_incomplete THEN 1 ELSE 0 END), 0) AS incomplete
    FROM curriculum_programoutcome po
    LEFT JOIN scoring_studentposcore s ON s.program_outcome_id = po.id
    GROUP BY po.id
"""


def create_view(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        if schema_editor.connection.vendor == "postgresql":
            cursor.execute(f"CREATE MATERIALIZED VIEW scoring_department_po_stats AS {SELECT_SQL}")
            # Needed for REFRESH ... CONCURRENTLY later and gives a primary-key style lookup.
            cursor.execute(
                "CREATE UNIQUE INDEX scoring_dept_po_stats_po_idx ON scoring_department_po_stats (program_outcome_id)"
            )
        else:
            cursor.execute(f"CREATE VIEW scoring_department_po_stats AS {SELECT_SQL}")


def drop_view(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        if schema_editor.connection.vendor == "postgresql":
            cursor.execute("DROP MATERIALIZED VIEW IF EXISTS scoring_department_po_stats")
        else:
            cursor.execute("DROP VIEW IF EXISTS scoring_department_po_stats")


class Migration(migrations.Migration):
    dependencies = [
        ("curriculum", "0001_initial"),
        ("scoring", "0002_remove_studentposcore_po_score_po_idx"),
    ]

    operations = [
        migrations.CreateModel(
            name="DepartmentPOStat",
            fields=[
                (
                    "program_outcome",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        primary_key=True,
                        serialize=False,
                        to="curriculum.programoutcome",
                    ),
                ),
                ("average", models.DecimalField(decimal_places=6, max_digits=12, null=True)),
                ("students", models.IntegerField()),
                ("incomplete", models.IntegerField()),
            ],
            options={
                "db_table": "scoring_department_po_stats",
                "managed": False,
            },
        ),
        migrations.RunPython(create_view, drop_view),
    ]
