from django.contrib import messages
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from accounts.models import User
from accounts.permissions import role_required
from alerts.services import send_pending_alerts, sync_alerts


@require_POST
@role_required(User.Role.ADMIN, User.Role.HEAD)
def send_alerts(request):
    synced = sync_alerts()
    sent = send_pending_alerts()
    messages.success(
        request,
        f"Alerts: {synced['created']} new, {synced['updated']} updated, {synced['deleted']} removed. "
        f"E-mails: {sent['sent']} sent, {sent['skipped']} skipped (no address), {sent['failed']} failed.",
    )
    return redirect("scoring:department_dashboard")
