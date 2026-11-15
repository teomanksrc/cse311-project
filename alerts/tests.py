from decimal import Decimal
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from alerts.models import POAlert
from alerts.services import send_pending_alerts, sync_alerts
from scoring.models import StudentPOScore


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AlertTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        cls.batuhan = User.objects.get(username="Batuhan")
        cls.ali = User.objects.get(username="Ali")

    def set_score(self, student, po_number, score):
        StudentPOScore.objects.filter(student=student, program_outcome__number=po_number).update(score=score)


class SyncTests(AlertTestBase):
    def test_demo_data_has_no_low_scores(self):
        self.assertEqual(sync_alerts(), {"created": 0, "updated": 0, "deleted": 0})

    def test_creates_updates_and_deletes(self):
        self.set_score(self.batuhan, 1, Decimal("50"))
        self.assertEqual(sync_alerts(), {"created": 1, "updated": 0, "deleted": 0})
        self.assertEqual(POAlert.objects.get().score, Decimal("50"))

        self.set_score(self.batuhan, 1, Decimal("40"))
        self.assertEqual(sync_alerts(), {"created": 0, "updated": 1, "deleted": 0})
        self.assertEqual(POAlert.objects.get().score, Decimal("40"))
        self.assertEqual(sync_alerts(), {"created": 0, "updated": 0, "deleted": 0})

        self.set_score(self.batuhan, 1, Decimal("60"))  # exactly the threshold is not low
        self.assertEqual(sync_alerts(), {"created": 0, "updated": 0, "deleted": 1})
        self.assertEqual(POAlert.objects.count(), 0)

    def test_alert_is_deleted_when_the_score_row_is_gone(self):
        self.set_score(self.batuhan, 1, Decimal("50"))
        sync_alerts()
        StudentPOScore.objects.filter(student=self.batuhan, program_outcome__number=1).delete()
        self.assertEqual(sync_alerts()["deleted"], 1)


class SendTests(AlertTestBase):
    def test_two_low_pos_make_one_message_and_a_second_run_sends_nothing(self):
        self.set_score(self.batuhan, 1, Decimal("50"))
        self.set_score(self.batuhan, 2, Decimal("45.54"))
        sync_alerts()
        self.assertEqual(send_pending_alerts(), {"sent": 1, "skipped": 0, "failed": 0})
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.batuhan.email])
        self.assertIn("PO1", message.body)
        self.assertIn("PO2", message.body)
        self.assertIn("50.0", message.body)
        self.assertIn("45.5", message.body)
        self.assertIn(reverse("reporting:my_report"), message.body)
        self.assertFalse(POAlert.objects.filter(emailed_at__isnull=True).exists())

        sync_alerts()
        self.assertEqual(send_pending_alerts(), {"sent": 0, "skipped": 0, "failed": 0})
        self.assertEqual(len(mail.outbox), 1)

    def test_student_without_email_is_skipped_and_stays_pending(self):
        self.set_score(self.batuhan, 1, Decimal("50"))
        User.objects.filter(pk=self.batuhan.pk).update(email="")
        sync_alerts()
        self.assertEqual(send_pending_alerts(), {"sent": 0, "skipped": 1, "failed": 0})
        self.assertEqual(len(mail.outbox), 0)
        self.assertIsNone(POAlert.objects.get().emailed_at)

    def test_message_contains_only_that_students_data(self):
        self.set_score(self.batuhan, 1, Decimal("50"))
        self.set_score(self.ali, 2, Decimal("33.3"))
        sync_alerts()
        self.assertEqual(send_pending_alerts()["sent"], 2)
        by_address = {m.to[0]: m for m in mail.outbox}
        own = by_address[self.batuhan.email].body
        self.assertIn("Batuhan", own)
        self.assertIn("50.0", own)
        self.assertNotIn("Ali", own)
        self.assertNotIn("33.3", own)
        self.assertNotIn("PO2", own)
        other = by_address[self.ali.email].body
        self.assertNotIn("Batuhan", other)
        self.assertNotIn("50.0", other)

    @override_settings(EMAIL_BACKEND="alerts.test_backends.Broken")
    def test_failed_send_is_not_marked_as_sent(self):
        self.set_score(self.batuhan, 1, Decimal("50"))
        sync_alerts()
        self.assertEqual(send_pending_alerts(), {"sent": 0, "skipped": 0, "failed": 1})
        self.assertIsNone(POAlert.objects.get().emailed_at)


class SendButtonTests(AlertTestBase):
    url = "/alerts/send/"

    def test_url_name_and_path(self):
        self.assertEqual(reverse("alerts:send"), self.url)

    def test_post_only(self):
        self.client.force_login(User.objects.get(username="head"))
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_admin_and_head_can_send_and_are_redirected_with_a_message(self):
        self.set_score(self.batuhan, 1, Decimal("50"))
        for username in ("admin", "head"):
            self.client.force_login(User.objects.get(username=username))
            response = self.client.post(self.url, follow=True)
            self.assertRedirects(response, reverse("scoring:department_dashboard"))
            self.assertContains(response, "E-mails:")
        self.assertEqual(len(mail.outbox), 1)  # the second click finds nothing new

    def test_students_and_instructors_get_403_and_anonymous_goes_to_login(self):
        for username in ("Batuhan", "instructor"):
            self.client.force_login(User.objects.get(username=username))
            self.assertEqual(self.client.post(self.url).status_code, 403, username)
        self.client.logout()
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_dashboard_shows_the_button_to_head(self):
        self.client.force_login(User.objects.get(username="head"))
        self.assertContains(self.client.get(reverse("scoring:department_dashboard")), "Send low-score alerts")


class CommandTests(AlertTestBase):
    def test_send_alerts_command(self):
        self.set_score(self.batuhan, 1, Decimal("50"))
        out = StringIO()
        call_command("send_alerts", stdout=out)
        self.assertIn("1 created", out.getvalue())
        self.assertIn("1 sent", out.getvalue())
        self.assertEqual(len(mail.outbox), 1)


class DashboardWarningTests(AlertTestBase):
    def test_warning_lists_low_pos(self):
        self.set_score(self.batuhan, 1, Decimal("50.04"))
        StudentPOScore.objects.filter(student=self.batuhan, program_outcome__number=2).update(
            score=Decimal("40"), is_incomplete=True
        )
        self.client.force_login(self.batuhan)
        response = self.client.get(reverse("scoring:student_dashboard"))
        self.assertContains(response, "Low score alert")
        self.assertContains(response, "50.0")
        self.assertContains(response, "some grades are missing")
        self.assertContains(response, reverse("reporting:my_report"))
        self.assertEqual([row["po"].number for row in response.context["low_scores"]], [1, 2])

    def test_no_warning_without_a_low_score(self):
        self.set_score(self.batuhan, 1, Decimal("30"))  # low for Batuhan only
        self.client.force_login(self.ali)
        self.assertNotContains(self.client.get(reverse("scoring:student_dashboard")), "Low score alert")
