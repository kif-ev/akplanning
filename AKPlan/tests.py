from unittest import mock
from zoneinfo import ZoneInfo

from datetime import datetime
from django.test import override_settings, TestCase
from django.urls import reverse

from AKModel.models import AK, AKSlot, Event, Room
from AKModel.tests.test_views import BasicViewTests


class PlanViewTests(BasicViewTests, TestCase):
    """
    Tests for AKPlan
    """
    fixtures = ['model.json']
    APP_NAME = 'plan'

    VIEWS = [
        ('plan_overview', {'event_slug': 'kif42'}),
        ('plan_wall', {'event_slug': 'kif42'}),
        ('plan_room', {'event_slug': 'kif42', 'pk': 2}),
        ('plan_track', {'event_slug': 'kif42', 'pk': 1}),
    ]

    def test_plan_hidden(self):
        """
        Test correct handling of plan visibility
        """
        _, url = self._name_and_url(('plan_overview', {'event_slug': 'kif23'}))

        self.client.logout()
        response = self.client.get(url)
        self.assertContains(response, "Plan is not visible (yet).",
                            msg_prefix="Plan is visible even though it shouldn't be")

        self.client.force_login(self.staff_user)
        response = self.client.get(url)
        self.assertNotContains(response, "Plan is not visible (yet).",
                               msg_prefix="Plan is not visible for staff user")

    def test_wall_redirect(self):
        """
        Test: Make sure that user is redirected from wall to overview when plan is hidden
        """
        _, url_wall = self._name_and_url(('plan_wall', {'event_slug': 'kif23'}))
        _, url_plan = self._name_and_url(('plan_overview', {'event_slug': 'kif23'}))

        response = self.client.get(url_wall)
        self.assertRedirects(response, url_plan,
                             msg_prefix=f"Redirect away from wall not working ({url_wall} -> {url_plan})")


WALL_TZ = ZoneInfo("Europe/Berlin")
WALL_NOW = datetime(2026, 11, 23, 18, 0, tzinfo=WALL_TZ)


class _FixedNowDatetime(datetime):
    """
    Datetime replacement with a fixed current time to make the wall view deterministic
    """

    @classmethod
    def now(cls, tz=None):
        return WALL_NOW if tz is None else WALL_NOW.astimezone(tz)


@override_settings(PLAN_WALL_VISIBLE_HOURS_AHEAD=12)
class PlanWallVisibleHoursTests(TestCase):
    """
    Tests for the restriction of the wall to the next visible hours
    """
    fixtures = ['model.json']

    def setUp(self):
        self.event = Event.objects.get(slug='kif42')
        self.event.start = datetime(2026, 11, 22, 8, tzinfo=WALL_TZ)
        self.event.end = datetime(2026, 11, 27, 20, tzinfo=WALL_TZ)
        self.event.active = True
        self.event.plan_hidden = False
        self.event.save()
        AKSlot.objects.filter(event=self.event).delete()
        ak = AK.objects.filter(event=self.event).first()
        assert ak is not None
        self.ak = ak

    def _get_wall_context(self):
        with mock.patch("AKPlan.views.datetime", _FixedNowDatetime):
            response = self.client.get(reverse('plan:plan_wall', kwargs={'event_slug': 'kif42'}))
        return response.context

    def _create_slot(self, room_name, day, hour, duration=2):
        room, _ = Room.objects.get_or_create(name=room_name, event=self.event, defaults={'capacity': 10})
        AKSlot.objects.create(ak=self.ak, event=self.event, room=room, duration=duration,
                              start=datetime(2026, 11, day, hour, tzinfo=WALL_TZ))

    def test_cutoff_beyond_current_day(self):
        """
        Test: If the visible hours cutoff lies on the next day, the wall contains the slots and rooms
        of the next day until the cutoff, but no later ones, and the plan ends at the cutoff
        (extended to the end of slots starting before the cutoff)
        """
        self._create_slot("R_today", 23, 19)
        self._create_slot("R_tomorrow", 24, 10)
        self._create_slot("R_tomorrow_late", 24, 16)
        self._create_slot("R_excluded", 24, 18)
        self._create_slot("R_day3", 25, 10)
        self._create_slot("R_day3", 25, 19)

        context = self._get_wall_context()

        # Visible daily range is 9:00-22:00, 12 visible hours from 18:00 hence end at 17:00 the next day
        self.assertEqual(context["earliest_start_hour"], 9)
        self.assertEqual(context["latest_end_hour"], 22)
        self.assertEqual({r.name for r in context["rooms"]}, {"R_today", "R_tomorrow", "R_tomorrow_late"},
                         msg="Wall does not contain exactly the rooms needed until the visible hours cutoff")
        self.assertEqual(len(context["akslots"]), 3)
        # Slot starting at 16:00 ends at 18:00, which extends the range beyond the cutoff
        self.assertEqual(context["end"], datetime(2026, 11, 24, 18, 0, tzinfo=WALL_TZ))

    def test_recent_slots(self):
        """
        Test: Slots that started before the retrospect range but did not end before its start are shown completely,
        slots that ended before are not shown
        """
        # Retrospect range starts at 15:00 (now is 18:00, see WALL_NOW)
        self._create_slot("R_old", 23, 12, duration=3)  # Ended exactly at 15:00
        self._create_slot("R_recent", 23, 14, duration=2)  # Started before, but ended within the range
        self._create_slot("R_running", 23, 13, duration=6)  # Started before and still running
        self._create_slot("R_later", 23, 19)

        with override_settings(PLAN_WALL_HOURS_RETROSPECT=3):
            context = self._get_wall_context()

        self.assertEqual({r.name for r in context["rooms"]}, {"R_recent", "R_running", "R_later"},
                         msg="Wall does not contain exactly the slots that did not end before the retrospect range")
        self.assertEqual([s.room.name for s in context["akslots_now"]], ["R_running"])
        # Plan starts early enough to show the earliest of these slots completely
        self.assertEqual(context["start"], datetime(2026, 11, 23, 13, 0, tzinfo=WALL_TZ))

    def test_visible_hours_normal_plan(self):
        """
        Test: The normal plan only shows the hours of the day in which slots take place
        """
        self._create_slot("R_morning", 23, 10)
        self._create_slot("R_evening", 24, 19, duration=1.5)
        # Ends in the hour after the evening slot (regression test: was not considered)
        self._create_slot("R_late", 25, 19, duration=2.5)

        response = self.client.get(reverse('plan:plan_overview', kwargs={'event_slug': 'kif42'}))
        # One hour before the earliest start and one after the latest end (since it is not a full hour)
        self.assertEqual(response.context["earliest_start_hour"], 9)
        self.assertEqual(response.context["latest_end_hour"], 22)
        self.assertContains(response, "slotMinTime: '9:00:00'")
        self.assertContains(response, "slotMaxTime: '22:00:00'")

    def test_reso_deadline_marker(self):
        """
        Test: The resolution deadline is marked in the plan and the wall (if set)
        """
        self._create_slot("R_today", 23, 19)
        url = reverse('plan:plan_overview', kwargs={'event_slug': 'kif42'})

        self.event.reso_deadline = None
        self.event.save()
        response = self.client.get(url)
        self.assertFalse([e for e in response.context["akslots_encoded"] if e.get('display') == 'background'])

        self.event.reso_deadline = datetime(2026, 11, 24, 12, 0, tzinfo=WALL_TZ)
        self.event.save()
        for context in [self.client.get(url).context, self._get_wall_context()]:
            markers = [e for e in context["akslots_encoded"] if e.get('display') == 'background']
            self.assertEqual(len(markers), 1)
            self.assertEqual(markers[0]['start'], "2026-11-24 12:00:00")
            self.assertEqual(markers[0]['classNames'], ['reso-deadline-marker'])
            self.assertNotIn('resourceId', markers[0], msg="Marker should be shown for all rooms")

    def test_no_cutoff_after_event(self):
        """
        Test: After the event, the visible hours restriction is not applied and the full wall is shown
        """
        self.event.start = datetime(2026, 11, 16, 8, tzinfo=WALL_TZ)
        self.event.end = datetime(2026, 11, 20, 20, tzinfo=WALL_TZ)
        self.event.save()

        self._create_slot("R_day1", 17, 10)
        self._create_slot("R_day2", 18, 10)
        self._create_slot("R_day3", 19, 19)

        context = self._get_wall_context()

        self.assertEqual({r.name for r in context["rooms"]}, {"R_day1", "R_day2", "R_day3"},
                         msg="Wall after the event does not contain all rooms")
        self.assertEqual(len(context["akslots"]), 3)
        self.assertEqual(context["start"], self.event.start)
        self.assertEqual(context["end"], self.event.end)

    @override_settings(PLAN_MAX_NEXT_AKS=2)
    def test_next_aks_limit(self):
        """
        Test: The list of next AKs contains at least PLAN_MAX_NEXT_AKS entries, in the normal plan more if there are
        more current AKs (entries beyond the limit are hidden on small screens), on the wall always exactly the limit
        """
        for i in range(4):
            self._create_slot(f"R_now{i}", 23, 17)
            self._create_slot(f"R_next{i}", 23, 19 + i % 2)

        with mock.patch("AKPlan.views.datetime", _FixedNowDatetime):
            response = self.client.get(reverse('plan:plan_overview', kwargs={'event_slug': 'kif42'}))
        # Show the same number of AKs current and next,
        # but with 2 of the next ones marked to only show on wider screens
        # since the setting for next AKs is only 2
        self.assertEqual(len(response.context["akslots_now"]), 4)
        self.assertEqual(len(response.context["akslots_next"]), 4)
        self.assertContains(response, 'class="d-none d-md-table-row"', count=2)

        # On the wall, the lists are below each other
        # and the next list should always stay at the limit
        context = self._get_wall_context()
        self.assertEqual(len(context["akslots_now"]), 4)
        self.assertEqual(len(context["akslots_next"]), 2)

        # If there is only 1 current AK (less than the limit from settings)
        # the list should neither be extended nor shortened
        AKSlot.objects.filter(room__name__in=["R_now0", "R_now1", "R_now2"]).delete()
        with mock.patch("AKPlan.views.datetime", _FixedNowDatetime):
            response = self.client.get(reverse('plan:plan_overview', kwargs={'event_slug': 'kif42'}))
        self.assertEqual(len(response.context["akslots_next"]), 2)
        self.assertNotContains(response, 'd-md-table-row')
