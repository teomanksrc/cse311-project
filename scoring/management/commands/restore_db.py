"""Restore a dump made by backup_db. DESTRUCTIVE: replaces the current contents of the database.

python manage.py restore_db backups/po_system_20261115_120000.dump --yes
"""

import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

DB_SERVICE = "db"  # service name in docker-compose.yml


class Command(BaseCommand):
    help = "Restore a pg_dump file into the database (drops and recreates the dumped objects)."

    def add_arguments(self, parser):
        parser.add_argument("file", help="Path to a .dump file made by backup_db")
        parser.add_argument("--yes", action="store_true", help="Confirm that the current data may be overwritten")

    def handle(self, *args, **options):
        if not options["yes"]:
            raise CommandError("This overwrites the current database. Run again with --yes to confirm.")
        if connection.vendor != "postgresql":
            raise CommandError("restore_db needs PostgreSQL.")
        source = Path(options["file"])
        if not source.is_file():
            raise CommandError(f"File not found: {source}")
        db = settings.DATABASES["default"]
        # --clean --if-exists drops each object before recreating it; --no-owner ignores who owned it.
        command = [
            "docker", "compose", "exec", "-T", DB_SERVICE,
            "pg_restore", "-U", db["USER"], "-d", db["NAME"], "--clean", "--if-exists", "--no-owner",
        ]  # fmt: skip
        try:
            with open(source, "rb") as dump:
                result = subprocess.run(command, stdin=dump, stderr=subprocess.PIPE, cwd=settings.BASE_DIR)
        except FileNotFoundError:
            raise CommandError("Docker is not installed or not on PATH.") from None
        if result.returncode != 0:
            message = result.stderr.decode(errors="replace").strip()
            raise CommandError(f"pg_restore failed: {message}")
        self.stdout.write(self.style.SUCCESS(f"Restored {source} into {db['NAME']}."))
