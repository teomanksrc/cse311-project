"""Print row count, columns and size of every application table: python manage.py db_stats"""

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Show rows, columns, table size, index size and total size per table (sizes: PostgreSQL only)."

    def handle(self, *args, **options):
        postgres = connection.vendor == "postgresql"
        header = ["table", "rows", "columns"] + (["table_size", "index_size", "total_size"] if postgres else [])
        lines = [header]
        for model in sorted(apps.get_models(include_auto_created=True), key=lambda m: m._meta.db_table):
            if not model._meta.managed:  # views have no storage of their own
                continue
            table = model._meta.db_table
            line = [table, str(model._default_manager.count()), str(len(model._meta.local_concrete_fields))]
            if postgres:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_size_pretty(pg_relation_size(%s::regclass)),"
                        " pg_size_pretty(pg_indexes_size(%s::regclass)),"
                        " pg_size_pretty(pg_total_relation_size(%s::regclass))",
                        [table, table, table],
                    )
                    line += list(cursor.fetchone())
            lines.append(line)
        widths = [max(len(row[i]) for row in lines) for i in range(len(header))]
        for row in lines:
            self.stdout.write("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip())
