"""Refresh the department statistics view: python manage.py refresh_stats"""

from django.core.management.base import BaseCommand

from scoring.stats import refresh_department_stats


class Command(BaseCommand):
    help = "Refresh scoring_department_po_stats (needed after edits made in the Django admin site)."

    def handle(self, *args, **options):
        refresh_department_stats()
        self.stdout.write(self.style.SUCCESS("Department statistics refreshed."))
