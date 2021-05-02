import pytz
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now

from AKModel.models import Event, AK, AKCategory


class DashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.event = Event.objects.create(
            name="Test Event",
            slug="test",
            timezone=pytz.utc,
            start=now(),
            end=now(),
            active=True,
        )
        cls.default_category = AKCategory.objects.create(
            name="Test Category",
            event=cls.event,
        )

    def test_dashboard_view(self):
        url = reverse('dashboard:dashboard_event', kwargs={"slug": self.event.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_nonexistent_dashboard_view(self):
        url = reverse('dashboard:dashboard_event', kwargs={"slug": "nonexistent-event"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_history(self):
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
