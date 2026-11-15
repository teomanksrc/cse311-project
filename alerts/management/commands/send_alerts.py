"""Sync low-score alerts and e-mail the new ones. This is what a scheduled job would run.

python manage.py send_alerts
"""

from django.core.management.base import BaseCommand

from alerts.services import send_pending_alerts, sync_alerts


class Command(BaseCommand):
    help = "Create/update/delete low-score alerts, then e-mail students about new ones."

    def handle(self, *args, **options):
        synced = sync_alerts()
        sent = send_pending_alerts()
        self.stdout.write(
            f"Alerts: {synced['created']} created, {synced['updated']} updated, {synced['deleted']} deleted."
        )
        self.stdout.write(
            f"E-mails: {sent['sent']} sent, {sent['skipped']} skipped (no address), {sent['failed']} failed."
        )
