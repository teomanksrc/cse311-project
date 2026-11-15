"""Back up the PostgreSQL database with pg_dump running inside the Docker container.

    python manage.py backup_db

Writes backups/<database>_<timestamp>.dump (pg_dump custom format, compressed).
Works the same on Windows and macOS: no shell syntax, only subprocess with a list of arguments.
"""

import subprocess
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

BACKUP_DIR = settings.BASE_DIR / "backups"
DB_SERVICE = "db"  # service name in docker-compose.yml


class Command(BaseCommand):
    help = "Dump the database to backups/ using pg_dump inside the Docker container."

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("backup_db needs PostgreSQL; the SQLite fallback is a single file you can copy.")
        db = settings.DATABASES["default"]
        BACKUP_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = BACKUP_DIR / f"{db['NAME']}_{stamp}.dump"
        command = ["docker", "compose", "exec", "-T", DB_SERVICE, "pg_dump", "-U", db["USER"], "-Fc", db["NAME"]]
        try:
            with open(target, "wb") as out:
                result = subprocess.run(command, stdout=out, stderr=subprocess.PIPE, cwd=settings.BASE_DIR)
        except FileNotFoundError:
            target.unlink(missing_ok=True)
            raise CommandError("Docker is not installed or not on PATH.") from None
        if result.returncode != 0:
            target.unlink(missing_ok=True)  # never leave an empty or partial file behind
            message = result.stderr.decode(errors="replace").strip()
            raise CommandError(f"pg_dump failed (is the '{DB_SERVICE}' container running?): {message}")
        self.stdout.write(self.style.SUCCESS(f"Backup written: {target} ({target.stat().st_size} bytes)"))
