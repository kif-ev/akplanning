from django.test import TestCase

from AKModel.tests import BasicViewTests


class PlanViewTests(BasicViewTests, TestCase):
    fixtures = ['model.json']
    APP_NAME = 'plan'

    VIEWS = [
        ('plan_overview', {'event_slug': 'kif42'}),
        ('plan_wall', {'event_slug': 'kif42'}),
        ('plan_room', {'event_slug': 'kif42', 'pk': 2}),
        ('plan_track', {'event_slug': 'kif42', 'pk': 1}),
    ]

    def testPlanHidden(self):
        view_name_with_prefix, url = self._name_and_url(('plan_overview', {'event_slug': 'kif23'}))

        self.client.logout()
        response = self.client.get(url)
        self.assertContains(response, "Plan is not visible (yet).",
                            msg_prefix="Plan is visible even though it shouldn't be")

        self.client.force_login(self.staff_user)
        response = self.client.get(url)
        self.assertNotContains(response, "Plan is not visible (yet).",
                               msg_prefix="Plan is not visible for staff user")
