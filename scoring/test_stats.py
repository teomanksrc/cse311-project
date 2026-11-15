"""Department statistics view, the refresh policy and the Refresh button."""

from decimal import Decimal
from io import StringIO
from unittest import skipUnless

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from curriculum.models import ProgramOutcome
from scoring.models import DepartmentPOStat, StudentPOScore
from scoring.stats import refresh_department_stats

IS_POSTGRES = connection.vendor == "postgresql"


class DepartmentStatsViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def test_view_has_one_row_per_po_with_correct_numbers(self):
        stats = {s.program_outcome.number: s for s in DepartmentPOStat.objects.select_related("program_outcome")}
        self.assertEqual(len(stats), 11)
        scores = list(StudentPOScore.objects.filter(program_outcome__number=1).values_list("score", flat=True))
        self.assertAlmostEqual(float(stats[1].average), float(sum(scores) / len(scores)), places=4)
        self.assertEqual(stats[1].students, 2)
        self.assertEqual(stats[1].incomplete, 0)
        self.assertIsNone(stats[8].average)  # LEFT JOIN: a PO without scores still has a row
        self.assertEqual((stats[8].students, stats[8].incomplete), (0, 0))

    def test_dashboard_shows_all_11_pos(self):
        self.client.force_login(User.objects.get(username="head"))
        response = self.client.get(reverse("scoring:department_dashboard"))
        self.assertEqual([r["po"].number for r in response.context["rows"]], list(range(1, 12)))

    @skipUnless(IS_POSTGRES, "a materialized view only exists on PostgreSQL; on SQLite the view is always current")
    def test_materialized_view_is_stale_until_refreshed(self):
        StudentPOScore.objects.filter(program_outcome__number=1).update(score=Decimal("10"))
        before = DepartmentPOStat.objects.get(program_outcome__number=1).average
        self.assertNotEqual(before, Decimal("10"))  # still the old snapshot
        refresh_department_stats()
        self.assertEqual(DepartmentPOStat.objects.get(program_outcome__number=1).average, Decimal("10"))

    def test_incomplete_count(self):
        StudentPOScore.objects.filter(program_outcome__number=1).update(is_incomplete=True)
        refresh_department_stats()
        self.assertEqual(DepartmentPOStat.objects.get(program_outcome__number=1).incomplete, 2)

    def test_refresh_stats_command_runs(self):
        call_command("refresh_stats", stdout=StringIO())

    def test_empty_po_table_gives_empty_view(self):
        ProgramOutcome.objects.all().delete()
        refresh_department_stats()
        self.assertEqual(DepartmentPOStat.objects.count(), 0)


class RefreshButtonTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def url(self):
        return reverse("scoring:refresh_department")

    def test_get_is_not_allowed(self):
        self.client.force_login(User.objects.get(username="head"))
        self.assertEqual(self.client.get(self.url()).status_code, 405)

    def test_head_and_admin_can_post_and_are_redirected(self):
        for username in ("head", "admin"):
            self.client.force_login(User.objects.get(username=username))
            response = self.client.post(self.url())
            self.assertRedirects(response, reverse("scoring:department_dashboard"), fetch_redirect_response=False)

    def test_other_roles_get_403_and_anonymous_is_sent_to_login(self):
        for username in ("instructor", "Batuhan"):
            self.client.force_login(User.objects.get(username=username))
            self.assertEqual(self.client.post(self.url()).status_code, 403, username)
        self.client.logout()
        self.assertEqual(self.client.post(self.url()).status_code, 302)

    @skipUnless(IS_POSTGRES, "needs a materialized view")
    def test_button_makes_admin_site_style_edits_visible(self):
        StudentPOScore.objects.filter(program_outcome__number=1).update(score=Decimal("10"))  # no view involved
        self.client.force_login(User.objects.get(username="head"))
        self.client.post(self.url())
        response = self.client.get(reverse("scoring:department_dashboard"))
        self.assertEqual({r["po"].number: r["average"] for r in response.context["rows"]}[1], 10.0)

    def test_dashboard_shows_the_button(self):
        self.client.force_login(User.objects.get(username="head"))
        response = self.client.get(reverse("scoring:department_dashboard"))
        self.assertContains(response, f'action="{self.url()}"')
