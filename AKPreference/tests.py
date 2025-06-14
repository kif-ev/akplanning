from django.urls import reverse
from django.test import TestCase

from AKModel.models import Event
from AKModel.tests.test_views import BasicViewTests

class PollViewTests(BasicViewTests, TestCase):
    """
    Tests for AKPreference Poll
    """
    fixtures = ['model.json']
    APP_NAME = 'poll'

    def test_poll_redirect(self):
        """
        Test: Make sure that user is redirected from poll to dashboard when poll is hidden
        """
        event = Event.objects.get(slug='kif42')
        _, url_poll = self._name_and_url(('poll', {'event_slug': event.slug}))
        url_dashboard = reverse("dashboard:dashboard_event", kwargs={"slug": event.slug})

        event.poll_hidden = True
        event.save()

        self.client.logout()
        response = self.client.get(url_poll)

        self.assertRedirects(response, url_dashboard,
                             msg_prefix=f"Redirect away from poll not working ({url_poll} -> {url_dashboard})")

        self.client.force_login(self.staff_user)
        response = self.client.get(url_poll)

        self.assertEqual(
            response.status_code,
            200,
            msg=f"{url_poll} broken",
        )

        self.assertTemplateUsed(response, "AKPreference/poll.html", msg_prefix="Poll is not visible for staff user")
