import zoneinfo
from django.apps import apps
from django.test import override_settings, TestCase
from django.urls import reverse
from django.utils.timezone import now
from typing import Any

from AKDashboard.models import DashboardButton, EventFact
from AKModel.models import AK, AKCategory, AKOwner, AKSlot, Event, Room
from AKModel.tests.test_views import BasicViewTests


class DashboardTests(TestCase):
    """
    Specific Dashboard Tests
    """
    # Set in setUpTestData
    event: Event
    default_category: AKCategory

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
                poll_hidden=False,
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
        self.assertQuerySetEqual(response.context["recent_changes"], [])

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
        self.assertFalse(self.event in response.context["active_and_current_events"])
        self.assertFalse(self.event in response.context["old_events"])
        response = self.client.get(url_event_dashboard)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["event"], self.event)

        # Public event -- should be part of the global dashboard
        self.event.public = True
        self.event.save()
        response = self.client.get(url_dashboard_index)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.event in response.context["active_and_current_events"])

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
            # Plan hidden? Button should not show
            self.event.plan_hidden = True
            self.event.save()
            response = self.client.get(url_event_dashboard)
            self.assertNotContains(response, "Schedule")

            # Plan not hidden?
            # Buttons for schedule should be on the page
            self.event.plan_hidden = False
            self.event.save()
            response = self.client.get(url_event_dashboard)
            self.assertContains(response, "Schedule")

    def test_poll_hidden(self):
        """
        Test visibility of poll buttons with regard to poll visibility status for a given event
        """
        url_event_dashboard = reverse('dashboard:dashboard_event', kwargs={"slug": self.event.slug})

        if apps.is_installed('AKPreference'):
            # Poll hidden? No buttons should show up
            self.event.poll_hidden = True
            self.event.save()
            response = self.client.get(url_event_dashboard)
            self.assertNotContains(response, "AK Preferences")

            # Poll not hidden?
            # Buttons to preference poll should be on the page
            self.event.poll_hidden = False
            self.event.save()
            response = self.client.get(url_event_dashboard)
            self.assertContains(response, "AK Preferences")

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
        ('dashboard_event_info', {'slug': 'kif42'}),
    ]


class DashboardEventInfoTests(TestCase):
    """
    Tests for the facts shown on the event info page
    """
    fixtures = ['model.json']

    def _get_facts(self, slug='kif42'):
        """
        Load the info page of the given event and return the facts shown, indexed by their title

        :param slug: slug of the event
        :return: facts as dict mapping title to tuple of value and detail,
            rankings are included as list of (name, explanation) tuples with the key "<title> ranking"
        :rtype: dict
        """
        response = self.client.get(reverse('dashboard:dashboard_event_info', kwargs={'slug': slug}))
        self.assertEqual(response.status_code, 200, msg="Info page not reachable")
        facts: dict[str, Any] = {}
        for fact in response.context['facts']:
            facts[str(fact['title'])] = (str(fact['value']), str(fact['detail']))
            if fact['ranking']:
                facts[f"{fact['title']} ranking"] = [(str(name), str(explanation))
                                                     for name, explanation in fact['ranking']]
        return facts

    def test_computed_facts(self):
        """
        Test that the computed facts are correct for the test event
        """
        facts = self._get_facts()

        self.assertIn("Plan published", facts)
        self.assertEqual(facts["Plan published"][1], "")
        self.assertEqual(facts["AKs"][0], "3")
        self.assertEqual(facts["AK Wishes"][0], "1")
        # 2 + 2 + 1.5 + 3 + 2 + 2 + 2 + 2 hours
        self.assertEqual(facts["Hours of AKs in total"][0], "16.5")
        # Owners "a" and "b"
        self.assertEqual(facts["Average length of AK owner names"], ("1", "character"))
        self.assertEqual(facts["Different institutions"][0], "2")
        # Ordered by name since both institutions have one AK owner
        self.assertEqual(facts["Different institutions ranking"],
                         [("Hochschule Y", "1 AK owner"), ("Uni X", "1 AK owner")])
        self.assertEqual(facts["Most AKs by one person"], ("a", "2 AKs: Test AK fixed slots, Test AK Inhalt"))
        self.assertEqual(facts["Most popular category"], ("Inhalt", "2 AKs"))
        # Categories with the same number of AKs are ordered by name
        self.assertEqual(facts["Most popular category ranking"],
                         [("Inhalt", "2 AKs"), ("Meta", "1 AK"), ("Spaß/Kultur", "1 AK")])
        self.assertEqual(facts["Longest AK name"], ("Test AK fixed slots", "19 characters"))
        self.assertEqual(facts["Shortest AK name"], ("AK Wish", "7 characters"))
        self.assertEqual(facts["Rooms"][0], "2")
        # Two scheduled slots of 2 hours each in "Testraum 2", only one in "Testraum"
        self.assertEqual(facts["Rooms ranking"], [("Testraum 2", "4 hours of AKs"), ("Testraum", "2 hours of AKs")])

    def test_ties_and_normalization(self):
        """
        Test that ties are shown with all names and that institutions are normalized
        """
        event = Event.get_by_slug('kif42')
        # Owner "b" now also has two AKs
        AK.objects.get(pk=3).owners.add(event.akowner_set.get(name='b'))
        # Same institution with different case and whitespace
        event.akowner_set.filter(name='b').update(institution=' uni x ')

        facts = self._get_facts()
        self.assertEqual(facts["Most AKs by one person"],
                         ("a, b", "2 AKs each – a: Test AK fixed slots, Test AK Inhalt; b: AK Wish, Test AK Meta"))
        self.assertEqual(facts["Different institutions"][0], "1")
        # Owners count for their institution, regardless of the number of AKs they offer
        self.assertEqual(facts["Different institutions ranking"], [("Uni X", "2 AK owners")])

    def test_top_three_institutions(self):
        """
        Test that only the three institutions with the most AK owners are shown
        """
        event = Event.get_by_slug('kif42')
        for i, institution in enumerate(["Uni Z", " uni z", "Hochschule Y", "Uni W", "Uni W", "Uni W", ""]):
            AKOwner.objects.create(name=f"Owner {i}", slug=f"owner-{i}", institution=institution, event=event)

        facts = self._get_facts()
        self.assertEqual(facts["Different institutions"][0], "4")
        # Different spellings are merged (showing the most common one), ties ordered by name
        self.assertEqual(facts["Different institutions ranking"],
                         [("Uni W", "3 AK owners"), ("Hochschule Y", "2 AK owners"), ("Uni Z", "2 AK owners")])

    def test_trashed_aks_are_ignored(self):
        """
        Test that trashed AKs (and their slots) are not considered
        """
        AK.objects.get(pk=4).move_to_trash()
        facts = self._get_facts()
        self.assertEqual(facts["AKs"][0], "2")
        self.assertEqual(facts["Most AKs by one person"], ("a, b", "1 AK each – a: Test AK Inhalt; b: Test AK Meta"))
        self.assertEqual(facts["Longest AK name"][0], "Test AK Inhalt")
        # Trashed AKs are not counted for their category
        self.assertEqual(facts["Most popular category ranking"],
                         [("Inhalt", "1 AK"), ("Meta", "1 AK"), ("Spaß/Kultur", "1 AK")])
        # Slots of AK 4 (3 * 2 hours) do not count
        self.assertEqual(facts["Hours of AKs in total"][0], "10.5")

    def test_top_three_rooms(self):
        """
        Test that only the three busiest rooms are shown (rooms with the same hours ordered by name)
        """
        event = Event.get_by_slug('kif42')
        ak = AK.objects.get(pk=1)
        for name, hours in [("Raum A", 3), ("Raum B", 2), ("Raum C", 0)]:
            room = Room.objects.create(name=name, capacity=10, event=event)
            if hours:
                AKSlot.objects.create(ak=ak, event=event, room=room, start=event.start, duration=hours)
        # Unscheduled slots do not count
        AKSlot.objects.create(ak=ak, event=event, room=Room.objects.get(name="Raum C"), duration=10)

        facts = self._get_facts()
        self.assertEqual(facts["Rooms"][0], "5")
        # "Raum B" and "Testraum" both have 2 hours, "Raum B" comes first by name
        self.assertEqual(facts["Rooms ranking"], [("Testraum 2", "4 hours of AKs"), ("Raum A", "3 hours of AKs"),
                                                  ("Raum B", "2 hours of AKs")])

    def test_hidden_plan(self):
        """
        Test that facts revealing the schedule are not shown as long as the plan is hidden
        """
        Event.objects.filter(slug='kif42').update(plan_hidden=True, plan_published_at=None)
        facts = self._get_facts()
        self.assertNotIn("Plan published", facts)
        self.assertEqual(facts["Rooms"][0], "2")
        self.assertNotIn("Rooms ranking", facts)

    def test_manual_facts(self):
        """
        Test that manually maintained facts are shown in the specified order
        """
        event = Event.get_by_slug('kif42')
        EventFact.objects.create(event=event, title="Coffee", value="40 l", order=2)
        EventFact.objects.create(event=event, title="Solver runs", value="17", icon="fas,cogs", order=1)

        response = self.client.get(reverse('dashboard:dashboard_event_info', kwargs={'slug': 'kif42'}))
        manual_facts = [(fact['title'], fact['value'], fact['icon']) for fact in response.context['facts']][-2:]
        self.assertEqual(manual_facts,
                         [("Solver runs", "17", ("cogs", "fas")), ("Coffee", "40 l", ("info-circle", "fas"))])
        self.assertContains(response, "Solver runs")

    def test_empty_event(self):
        """
        Test that the info page also works for an event without any data
        """
        Event.objects.create(name="Empty Event", slug="empty", start=now(), end=now(), active=True)
        facts = self._get_facts('empty')
        self.assertEqual(facts["AKs"][0], "0")
        self.assertNotIn("Hours of AKs in total", facts)
        self.assertNotIn("Most AKs by one person", facts)

    def test_german_translation(self):
        """
        Test that the info page is translated, including localized numbers and plural forms
        """
        response = self.client.get(reverse('dashboard:dashboard_event_info', kwargs={'slug': 'kif42'}),
                                   headers={'accept-language': 'de'})
        self.assertContains(response, "Plan veröffentlicht")
        self.assertContains(response, "16,5")
        self.assertContains(response, "2 AKs")
        self.assertContains(response, "19 Zeichen")
