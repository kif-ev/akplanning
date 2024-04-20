import zoneinfo
from django.apps import apps
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.timezone import now

from AKDashboard.models import DashboardButton
from AKModel.models import Event, AK, AKCategory
from AKModel.tests import BasicViewTests


class DashboardTests(TestCase):
    """
    Specific Dashboard Tests
    """
    @classmethod
    def setUpTestData(cls):
        """
        Initialize Test database
        """
        super().setUpTestData()
        cls.event = Event.objects.create(
            name="Dashboard Test Event",
            slug="dashboardtest",
            timezone=zoneinfo.ZoneInfo("Europe/Berlin"),
            start=now(),
            end=now(),
            active=True,
            plan_hidden=False,
        )
        cls.default_category = AKCategory.objects.create(
            name="Test Category",
            event=cls.event,
        )

    def test_dashboard_view(self):
        """
        Check that the main dashboard is reachable
        (would also be covered by generic view testcase below)
        """
        url = reverse('dashboard:dashboard_event', kwargs={"slug": self.event.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_nonexistent_dashboard_view(self):
        """
        Make sure there is no dashboard for an non-existing event
        """
        url = reverse('dashboard:dashboard_event', kwargs={"slug": "nonexistent-event"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    @override_settings(DASHBOARD_SHOW_RECENT=True)
    def test_history(self):
        """
        Test displaying of history

        For the sake of that test, the setting to show recent events in dashboard is enforced to be true
        regardless of the default configuration currently in place
        """
        url = reverse('dashboard:dashboard_event', kwargs={"slug": self.event.slug})

        # History should be empty
        response = self.client.get(url)
        self.assertQuerysetEqual(response.context["recent_changes"], [])

        AK.objects.create(
            name="Test AK",
            category=self.default_category,
            event=self.event,
        )

        # History should now contain one AK (Test AK)
        response = self.client.get(url)
        self.assertEqual(len(response.context["recent_changes"]), 1)
        self.assertEqual(response.context["recent_changes"][0]['text'], "New AK: Test AK.")

    def test_public(self):
        """
        Test handling of public and private events
        (only public events should be part of the standard dashboard,
        but there should be an individual dashboard for both public and private events)
        """
        url_dashboard_index = reverse('dashboard:dashboard')
        url_event_dashboard = reverse('dashboard:dashboard_event', kwargs={"slug": self.event.slug})

        # Non-Public event (should not be part of the global dashboard
        # but should have an individual dashboard page for those knowing the url)
        self.event.public = False
        self.event.save()
        response = self.client.get(url_dashboard_index)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.event in response.context["events"])
        response = self.client.get(url_event_dashboard)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["event"], self.event)

        # Public event -- should be part of the global dashboard
        self.event.public = True
        self.event.save()
        response = self.client.get(url_dashboard_index)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.event in response.context["events"])

    def test_active(self):
        """
        Test existence of buttons with regard to activity status of the given event
        """
        url_event_dashboard = reverse('dashboard:dashboard_event', kwargs={"slug": self.event.slug})

        if apps.is_installed('AKSubmission'):
            # Non-active event -> No submission
            self.event.active = False
            self.event.save()
            response = self.client.get(url_event_dashboard)
            self.assertNotContains(response, "AK Submission")

            # Active event -> Submission should be open
            self.event.active = True
            self.event.save()
            response = self.client.get(url_event_dashboard)
            self.assertContains(response, "AK Submission")

    def test_plan_hidden(self):
        """
        Test visibility of plan buttons with regard to plan visibility status for a given event
        """
        url_event_dashboard = reverse('dashboard:dashboard_event', kwargs={"slug": self.event.slug})

        if apps.is_installed('AKPlan'):
            # Plan hidden? No buttons should show up
            self.event.plan_hidden = True
            self.event.save()
            response = self.client.get(url_event_dashboard)
            self.assertNotContains(response, "Current AKs")
            self.assertNotContains(response, "AK Wall")

            # Plan not hidden?
            # Buttons for current AKs and AK Wall should be on the page
            self.event.plan_hidden = False
            self.event.save()
            response = self.client.get(url_event_dashboard)
            self.assertContains(response, "Current AKs")
            self.assertContains(response, "AK Wall")

    def test_dashboard_buttons(self):
        """
        Make sure manually added buttons are displayed correctly
        """
        url_event_dashboard = reverse('dashboard:dashboard_event', kwargs={"slug": self.event.slug})

        response = self.client.get(url_event_dashboard)
        self.assertNotContains(response, "Dashboard Button Test")

        DashboardButton.objects.create(
            text="Dashboard Button Test",
            event=self.event
        )

        response = self.client.get(url_event_dashboard)
        self.assertContains(response, "Dashboard Button Test")


class DashboardViewTests(BasicViewTests, TestCase):
    """
    Generic view tests, based on :class:`AKModel.BasicViewTests` as specified in this class in VIEWS
    """
    fixtures = ['model.json', 'dashboard.json']

    APP_NAME = 'dashboard'

    VIEWS = [
        ('dashboard', {}),
        ('dashboard_event', {'slug': 'kif42'}),
    ]
