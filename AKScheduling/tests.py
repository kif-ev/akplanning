import json
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from AKModel.tests.test_views import BasicViewTests
from AKModel.models import AKSlot, Event, Room, AK, AKCategory, AKRequirement
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
            content_type = 'application/json'
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
            content_type = 'application/json'
        )
        self.assertEqual(response.status_code, 200, "Second PUT to API endpoint did not work")

        # Make sure API call did update the slot as expected
        slot = AKSlot.objects.get(pk=pk)
        self.assertEqual(new_room.pk, slot.room.pk, "Update did not work")

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
