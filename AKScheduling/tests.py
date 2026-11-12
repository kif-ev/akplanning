import html
import json
import re
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from AKModel.models import AK, AKCategory, AKRequirement, AKSlot, AKTrack, ConstraintViolation, Event, Room
from AKModel.tests.test_views import BasicViewTests
from AKScheduling.checks import aks_with_unfulfillable_requirements


class ModelViewTests(BasicViewTests, TestCase):
    """
    Tests for AKScheduling
    """
    fixtures = ['model.json']

    VIEWS_STAFF_ONLY = [
        # Views
        ('admin:schedule', {'event_slug': 'kif42'}),
        ('admin:slots_unscheduled', {'event_slug': 'kif42'}),
        ('admin:constraint-violations', {'slug': 'kif42'}),
        ('admin:special-attention', {'slug': 'kif42'}),
        ('admin:cleanup-wish-slots', {'event_slug': 'kif42'}),
        ('admin:autocreate-availabilities', {'event_slug': 'kif42'}),
        ('admin:tracks_manage', {'event_slug': 'kif42'}),
        ('admin:enter-interest', {'event_slug': 'kif42', 'pk': 1}),
        # API (Read)
        ('model:scheduling-resources-list', {'event_slug': 'kif42'}, 403),
        ('model:scheduling-constraint-violations-list', {'event_slug': 'kif42'}, 403),
        ('model:scheduling-events', {'event_slug': 'kif42'}),
        ('model:scheduling-room-availabilities', {'event_slug': 'kif42'}),
        ('model:scheduling-default-slots', {'event_slug': 'kif42'}),
    ]

    def test_scheduling_of_slot_update(self):
        """
        Test rescheduling a slot to a different time or room
        """
        self.client.force_login(self.admin_user)

        event = Event.get_by_slug('kif42')

        # Get the first already scheduled slot belonging to this event
        slot = event.akslot_set.filter(start__isnull=False).first()
        pk = slot.pk
        room_id = slot.room_id
        events_api_url = f"/kif42/api/scheduling-event/{pk}/"

        # Create updated time
        offset = timedelta(hours=1)
        new_start_time = slot.start + offset
        new_end_time = slot.end + offset
        new_start_time_string = timezone.localtime(new_start_time, event.timezone).strftime("%Y-%m-%d %H:%M:%S")
        new_end_time_string = timezone.localtime(new_end_time, event.timezone).strftime("%Y-%m-%d %H:%M:%S")

        # Try API call
        response = self.client.put(
                events_api_url,
                json.dumps({
                    'start': new_start_time_string,
                    'end': new_end_time_string,
                    'roomId': room_id,
                }),
                content_type='application/json'
        )
        self.assertEqual(response.status_code, 200, "PUT to API endpoint did not work")

        # Make sure API call did update the slot as expected
        slot = AKSlot.objects.get(pk=pk)
        self.assertEqual(new_start_time, slot.start, "Update did not work")

        # Test updating room
        new_room = Room.objects.exclude(pk=room_id).first()

        # Try second API call
        response = self.client.put(
                events_api_url,
                json.dumps({
                    'start': new_start_time_string,
                    'end': new_end_time_string,
                    'roomId': new_room.pk,
                }),
                content_type='application/json'
        )
        self.assertEqual(response.status_code, 200, "Second PUT to API endpoint did not work")

        # Make sure API call did update the slot as expected
        slot = AKSlot.objects.get(pk=pk)
        self.assertEqual(new_room.pk, slot.room.pk, "Update did not work")

    def test_unscheduling_of_slot(self):
        """
        Test removing a slot from the schedule (e.g., by dragging it back to the list of unscheduled slots)
        """
        event = Event.get_by_slug('kif42')
        slot = event.akslot_set.filter(start__isnull=False, room__isnull=False, fixed=False).first()
        unschedule_url = f"/kif42/api/scheduling-event/{slot.pk}/unschedule/"

        # Not possible without login
        response = self.client.post(unschedule_url)
        self.assertEqual(response.status_code, 403, "Unscheduling possible without login")
        slot.refresh_from_db()
        self.assertIsNotNone(slot.start)

        self.client.force_login(self.admin_user)
        response = self.client.post(unschedule_url)
        self.assertEqual(response.status_code, 200, "POST to unschedule endpoint did not work")
        slot.refresh_from_db()
        self.assertIsNone(slot.start, "Slot was not unscheduled")
        self.assertIsNone(slot.room, "Room of slot was not reset")

        # Fixed slots cannot be unscheduled
        fixed_slot = event.akslot_set.filter(start__isnull=False).exclude(pk=slot.pk).first()
        AKSlot.objects.filter(pk=fixed_slot.pk).update(fixed=True)
        response = self.client.post(f"/kif42/api/scheduling-event/{fixed_slot.pk}/unschedule/")
        self.assertEqual(response.status_code, 400, "Fixed slot could be unscheduled")
        fixed_slot.refresh_from_db()
        self.assertIsNotNone(fixed_slot.start)

        # Slots of other events cannot be unscheduled via this event
        other_slot = AKSlot.objects.exclude(event=event).first()
        response = self.client.post(f"/kif42/api/scheduling-event/{other_slot.pk}/unschedule/")
        self.assertEqual(response.status_code, 404, "Slot of other event could be unscheduled")

    def test_unscheduled_slot_drag_data(self):
        """
        Test that the data of unscheduled slots in the scheduling view (used to create calendar events when dropping
        them on the calendar) is valid JSON and contains everything needed to unschedule them again later
        """
        event = Event.get_by_slug('kif42')
        slot = event.akslot_set.filter(start__isnull=False, fixed=False).first()
        # Track name with characters that need escaping
        track = AKTrack.objects.create(name='Track "with" \'quotes\'', event=event)
        AK.objects.filter(pk=slot.ak_id).update(track=track)
        AKSlot.objects.filter(pk=slot.pk).update(start=None, room=None)

        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('admin:schedule', kwargs={'event_slug': 'kif42'}))
        self.assertEqual(response.status_code, 200)

        drag_data = [json.loads(html.unescape(data))
                     for data in re.findall(r"data-event='([^']*)'", response.content.decode())]
        self.assertGreater(len(drag_data), 0, "No unscheduled slots found")
        for data in drag_data:
            for key in ['title', 'duration', 'slotID', 'shortName', 'ownersList', 'slotDuration', 'trackId',
                        'trackName', 'description', 'url']:
                self.assertIn(key, data, f"Missing {key} in data for dropping slot {data.get('slotID')}")

        data = next(d for d in drag_data if d['slotID'] == str(slot.pk))
        self.assertEqual(data['trackId'], track.pk)
        self.assertEqual(data['trackName'], track.name)
        self.assertEqual(data['slotDuration'], float(slot.duration))

    def test_constraint_violation_resolution_in_api(self):
        """
        Test that the constraint violations API includes who resolved a violation manually and why
        """
        ConstraintViolation.objects.filter(pk=1).update(manually_resolved=True, resolved_by=self.admin_user,
                                                        resolution_reason="Discussed with <b>AK owners</b>")
        ConstraintViolation.objects.filter(pk=2).update(manually_resolved=True)

        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('model:scheduling-constraint-violations-list',
                                           kwargs={'event_slug': 'kif42'}))
        self.assertEqual(response.status_code, 200)
        cvs = {cv['pk']: cv for cv in response.json()}

        self.assertEqual(cvs[1]['resolved_by_display'], "Test Admin User")
        self.assertEqual(cvs[1]['resolution_reason'], "Discussed with <b>AK owners</b>")
        self.assertEqual(cvs[1]['resolution_display'], "Resolved by Test Admin User: Discussed with <b>AK owners</b>")
        # Resolved without known user and reason (e.g., resolved before this was tracked)
        self.assertEqual(cvs[2]['resolution_display'], "Manually Resolved")
        # Not resolved
        self.assertEqual(cvs[3]['resolution_display'], "")

    def test_aks_unfulfillable_requirements(self):
        """
        Test detection of AKs with unfulfillable requirements
        """
        event = Event.objects.get(pk=2)
        aks_unfulfillable_requirements = aks_with_unfulfillable_requirements(event)
        self.assertEqual(len(aks_unfulfillable_requirements), 0,
                         "Wrongly identified AKs with fulfillable requirements as unfulfillable")

        # Create an AK with an unfulfillable requirement (that is not property of any room)
        ak = AK.objects.create(
                event=event,
                name="Test AK with unfulfillable requirement",
                category=AKCategory.objects.filter(event=event).first(),
                include_in_export=True,
        )
        req = AKRequirement.objects.create(
                event=event,
                name="Unfulfillable Requirement",
        )
        ak.requirements.add(req)

        ak2 = AK.objects.get(pk=1)
        ak2.requirements.add(AKRequirement.objects.get(pk=5))

        aks_unfulfillable_requirements = aks_with_unfulfillable_requirements(event)
        self.assertEqual(len(aks_unfulfillable_requirements), 2,
                         "Failed to identify AKs with unfulfillable requirements")
        self.assertIn(ak, aks_unfulfillable_requirements,
                      "Missed new AK with requirement not set for any room")
        self.assertIn(ak2, aks_unfulfillable_requirements,
                      "Missed existing AK with invalid requirement combination")

        aks_unfulfillable_requirements_filtered = aks_with_unfulfillable_requirements(
                event,
                qs=event.ak_set.exclude(category__in=[AKCategory.objects.filter(event=event).first()])
        )
        self.assertNotIn(ak, aks_unfulfillable_requirements_filtered,
                         "Filtering did not work correctly")
