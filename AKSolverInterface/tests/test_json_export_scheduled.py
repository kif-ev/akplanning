from datetime import datetime, timedelta, timezone
from django.test import TestCase

from AKModel.availability.models import Availability
from AKModel.models import AK, AKSlot, Event
from AKPreference.models import EventParticipant
from AKSolverInterface.serializers import ExportEventSerializer


class JSONExportScheduledSlotsTest(TestCase):
    """Test that scheduled slots are removed from the export when fixing scheduled slots
    and that availabilities of affected objects are reduced accordingly."""

    fixtures = ["model.json"]

    def setUp(self):
        self.event = Event.objects.get(pk=2)
        # AK 3 conflicts with AK 1 and has AK 2 as prerequisite
        self.ak_wish = AK.objects.get(pk=3)
        Availability.with_event_length(event=self.event, ak=self.ak_wish).save()
        self.scheduled_slots = list(AKSlot.objects.filter(event=self.event, start__isnull=False))

    def _slot_avail(self, slot: AKSlot) -> Availability:
        """Availability covering the time of the given scheduled slot"""
        return Availability(event=self.event, start=slot.scheduled_start, end=slot.scheduled_end)

    def _export(self, fixed: bool) -> dict:
        return ExportEventSerializer(self.event, export_scheduled_aks_as_fixed=fixed).data

    @staticmethod
    def _timeslots(export: dict):
        for block in export["timeslots"]["blocks"]:
            yield from block

    def _timeslot_avail(self, timeslot: dict) -> Availability:
        def _parse(value: str) -> datetime:
            return datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=self.event.timezone)

        return Availability(event=self.event, start=_parse(timeslot["info"]["start"]),
                            end=_parse(timeslot["info"]["end"]))

    def _fulfilling_timeslots(self, export: dict, constraint: str) -> list[Availability]:
        return [
            self._timeslot_avail(timeslot) for timeslot in self._timeslots(export)
            if constraint in timeslot["fulfilled_time_constraints"]
        ]

    def test_scheduled_slots_removed(self):
        """Scheduled slots are only exported if scheduled slots are not fixed."""
        scheduled_pks = {slot.pk for slot in self.scheduled_slots}
        self.assertTrue(scheduled_pks <= {ak["id"] for ak in self._export(fixed=False)["aks"]})

        export = self._export(fixed=True)
        exported_pks = {ak["id"] for ak in export["aks"]}
        self.assertFalse(scheduled_pks & exported_pks)
        for participant in export["participants"]:
            self.assertFalse(scheduled_pks & {pref["ak_id"] for pref in participant["preferences"]})

    def test_owner_availability_reduced(self):
        """Owners are not available during their scheduled slots."""
        export = self._export(fixed=True)
        for slot in self.scheduled_slots:
            slot_avail = self._slot_avail(slot)
            for owner in slot.ak.owners.all():
                with self.subTest(slot=slot, owner=owner):
                    timeslots = self._fulfilling_timeslots(export, f"availability-person-{owner.pk}")
                    self.assertTrue(timeslots)
                    self.assertFalse(any(t.overlaps(slot_avail, strict=True) for t in timeslots))
        # remaining slot of AK 1 is constrained by its owner
        remaining_slot = next(ak for ak in export["aks"] if ak["id"] == 5)
        self.assertIn("availability-person-1", remaining_slot["time_constraints"])

    def test_room_availability_reduced(self):
        """Rooms are not available during slots scheduled in them."""
        slots_with_room = [slot for slot in self.scheduled_slots if slot.room is not None]
        self.assertTrue(slots_with_room)
        for slot in slots_with_room:
            Availability.with_event_length(event=self.event, room=slot.room).save()
        unfixed_rooms = {room["id"]: room for room in self._export(fixed=False)["rooms"]}
        for slot in slots_with_room:
            self.assertFalse(unfixed_rooms[slot.room_id]["time_constraints"])

        export = self._export(fixed=True)
        for slot in slots_with_room:
            with self.subTest(slot=slot):
                constraint = f"availability-room-{slot.room_id}"
                room = next(r for r in export["rooms"] if r["id"] == slot.room_id)
                self.assertIn(constraint, room["time_constraints"])
                slot_avail = self._slot_avail(slot)
                timeslots = self._fulfilling_timeslots(export, constraint)
                self.assertTrue(timeslots)
                self.assertFalse(any(t.overlaps(slot_avail, strict=True) for t in timeslots))

    def test_owner_without_remaining_availability(self):
        """Owners whose whole availability is used by scheduled slots cannot be scheduled anymore."""
        slot = AKSlot.objects.get(pk=2)
        owner = slot.ak.owners.get()
        slot_avail = self._slot_avail(slot)
        Availability.objects.create(event=self.event, person=owner, start=slot_avail.start, end=slot_avail.end)
        # unscheduled slot of the same owner
        AKSlot.objects.create(event=self.event, ak=slot.ak, duration=1)

        export = self._export(fixed=True)
        constraint = f"availability-person-{owner.pk}"
        for ak in export["aks"]:
            if ak["info"]["django_ak_id"] == slot.ak.pk:
                self.assertIn(constraint, ak["time_constraints"])
        self.assertFalse(self._fulfilling_timeslots(export, constraint))

    def test_linked_participant_availability_reduced(self):
        """Participants linked to an AK owner are not available during scheduled slots of that owner."""
        slot = AKSlot.objects.get(pk=2)
        owner = slot.ak.owners.first()
        participant = EventParticipant.objects.create(event=self.event, name="Owner participant", ak_owner=owner)
        constraint = f"availability-participant-{participant.pk}"

        export = self._export(fixed=False)
        export_participant = next(p for p in export["participants"] if p["id"] == participant.pk)
        self.assertNotIn(constraint, export_participant["time_constraints"])

        export = self._export(fixed=True)
        export_participant = next(p for p in export["participants"] if p["id"] == participant.pk)
        self.assertIn(constraint, export_participant["time_constraints"])
        timeslots = self._fulfilling_timeslots(export, constraint)
        self.assertTrue(timeslots)
        for scheduled_slot in AKSlot.objects.filter(event=self.event, start__isnull=False, ak__owners=owner):
            scheduled_avail = self._slot_avail(scheduled_slot)
            self.assertFalse(any(t.overlaps(scheduled_avail, strict=True) for t in timeslots))

    def test_linked_participant_availability_restricts_owned_aks(self):
        """Availabilities of participants linked to an AK owner restrict when the AKs of that owner can take place,
        but not the AKs they would like to attend."""
        slot = AKSlot.objects.get(pk=2)
        owner = slot.ak.owners.first()
        assert owner is not None
        participant = EventParticipant.objects.create(event=self.event, name="Owner participant", ak_owner=owner)
        # unscheduled slot of the owner, so it is also exported when fixing scheduled slots
        unscheduled_slot = AKSlot.objects.create(event=self.event, ak=slot.ak, duration=1)
        # the participant is only available during the second day, which contains the scheduled slot
        participant_avail = Availability(event=self.event, start=datetime(2020, 11, 8, 8, tzinfo=timezone.utc),
                                         end=datetime(2020, 11, 8, 19, tzinfo=timezone.utc))
        Availability.objects.create(event=self.event, participant=participant,
                                    start=participant_avail.start, end=participant_avail.end)
        slot_avail = self._slot_avail(slot)

        for fixed in [False, True]:
            with self.subTest(fixed=fixed):
                export = self._export(fixed=fixed)
                constraint = f"availability-person-{owner.pk}"
                exported_slot = next(ak for ak in export["aks"] if ak["id"] == unscheduled_slot.pk)
                self.assertIn(constraint, exported_slot["time_constraints"])
                timeslots = self._fulfilling_timeslots(export, constraint)
                self.assertTrue(timeslots)
                self.assertTrue(all(t.is_covered([participant_avail]) for t in timeslots))
                if fixed:
                    self.assertFalse(any(t.overlaps(slot_avail, strict=True) for t in timeslots))

                export_participant = next(p for p in export["participants"] if p["id"] == participant.pk)
                self.assertFalse([c for c in export_participant["time_constraints"]
                                  if c.startswith("availability-person-")])

    def test_linked_participant_availability_ignored_without_preferences(self):
        """Availabilities of participants linked to an AK owner are ignored if preferences are not exported."""
        slot = AKSlot.objects.get(pk=2)
        participant = EventParticipant.objects.create(event=self.event, name="Owner participant",
                                                      ak_owner=slot.ak.owners.first())
        AKSlot.objects.create(event=self.event, ak=slot.ak, duration=1)

        for fixed in [False, True]:
            with self.subTest(fixed=fixed):
                Availability.objects.filter(participant=participant).delete()
                expected = ExportEventSerializer(self.event, export_scheduled_aks_as_fixed=fixed,
                                                 export_preferences=False).data
                Availability.objects.create(event=self.event, participant=participant,
                                            start=datetime(2020, 11, 8, 8, tzinfo=timezone.utc),
                                            end=datetime(2020, 11, 8, 19, tzinfo=timezone.utc))
                export = ExportEventSerializer(self.event, export_scheduled_aks_as_fixed=fixed,
                                               export_preferences=False).data
                self.assertEqual(expected, export)

    def test_prerequisite_ak_availability_reduced(self):
        """Prerequisites of a scheduled AK are only available before its start."""
        # schedule a slot of AK 3, which has AK 2 as prerequisite
        AKSlot.objects.get(pk=2).unschedule()
        Availability.with_event_length(event=self.event, ak=AK.objects.get(pk=2)).save()
        wish_slot = AKSlot.objects.get(pk=3)
        wish_slot.start = datetime(2020, 11, 8, 12, 0, tzinfo=timezone.utc)
        wish_slot.save()

        timeslots = self._fulfilling_timeslots(self._export(fixed=True), "availability-ak-2")
        self.assertTrue(timeslots)
        self.assertTrue(all(t.end <= wish_slot.start for t in timeslots))

    def test_filtered_scheduled_slots_considered(self):
        """Scheduled slots excluded by filters still reduce availabilities."""
        slot = AKSlot.objects.get(pk=2)
        owner = slot.ak.owners.get()
        slot_avail = self._slot_avail(slot)

        export = ExportEventSerializer(
                self.event, export_scheduled_aks_as_fixed=True,
                filter_slots_cb=lambda queryset: queryset.exclude(ak=slot.ak),
        ).data
        timeslots = self._fulfilling_timeslots(export, f"availability-person-{owner.pk}")
        self.assertTrue(timeslots)
        self.assertFalse(any(t.overlaps(slot_avail, strict=True) for t in timeslots))

    def test_no_fixed_slot_constraints(self):
        """Timeslots do not fulfill constraints of fixed slots that are not exported."""
        export = self._export(fixed=True)
        for timeslot in self._timeslots(export):
            self.assertFalse([c for c in timeslot["fulfilled_time_constraints"] if c.startswith("fixed-akslot-")])

    def test_dependent_ak_availability_reduced(self):
        """AKs depending on a scheduled AK are only available after its end."""
        export = self._export(fixed=True)
        prerequisite_end = AKSlot.objects.get(pk=2).scheduled_end
        timeslots = self._fulfilling_timeslots(export, "availability-ak-3")
        self.assertTrue(timeslots)
        self.assertTrue(all(t.start >= prerequisite_end for t in timeslots))
        for ak in export["aks"]:
            if ak["info"]["django_ak_id"] == 3:
                self.assertIn("availability-ak-3", ak["time_constraints"])

    def test_conflicting_ak_availability_reduced_both_ways(self):
        """Conflicts are considered in both directions."""
        # move slot of AK 1 (conflicting with AK 3) into the timeslots
        slot = AKSlot.objects.get(pk=1)
        slot.start = datetime(2020, 11, 9, 20, 0, tzinfo=timezone.utc)
        slot.save()
        slot_avail = self._slot_avail(slot)

        timeslots = self._fulfilling_timeslots(self._export(fixed=True), "availability-ak-3")
        self.assertTrue(timeslots)
        self.assertFalse(any(t.overlaps(slot_avail, strict=True) for t in timeslots))

        # AK 1 is not available during a scheduled slot of AK 3
        slot.unschedule()
        Availability.with_event_length(event=self.event, ak=slot.ak).save()
        wish_slot = AKSlot.objects.get(pk=3)
        wish_slot.start = datetime(2020, 11, 9, 20, 0, tzinfo=timezone.utc)
        wish_slot.save()
        wish_avail = self._slot_avail(wish_slot)

        timeslots = self._fulfilling_timeslots(self._export(fixed=True), "availability-ak-1")
        self.assertTrue(timeslots)
        self.assertFalse(any(t.overlaps(wish_avail, strict=True) for t in timeslots))


class AvailabilityDifferenceTest(TestCase):
    """Test computing the difference of availabilities."""

    def test_difference(self):
        """Test the difference of availabilities for disjoint, overlapping and contained availabilities."""
        base = datetime(2020, 1, 1, tzinfo=timezone.utc)

        def _avail(start_hour: int, end_hour: int) -> Availability:
            return Availability(start=base + timedelta(hours=start_hour), end=base + timedelta(hours=end_hour))

        def _hours(avails: list[Availability]) -> list[tuple[int, int]]:
            return [(int((a.start - base).total_seconds() // 3600), int((a.end - base).total_seconds() // 3600))
                    for a in avails]

        self.assertEqual(_hours(Availability.difference([_avail(0, 10)], [_avail(2, 4)])), [(0, 2), (4, 10)])
        self.assertEqual(_hours(Availability.difference([_avail(0, 10)], [_avail(0, 4), _avail(8, 12)])),
                         [(4, 8)])
        self.assertEqual(_hours(Availability.difference([_avail(0, 2), _avail(5, 7)], [_avail(1, 6)])),
                         [(0, 1), (6, 7)])
        self.assertEqual(_hours(Availability.difference([_avail(0, 2)], [_avail(2, 4)])), [(0, 2)])
        self.assertEqual(Availability.difference([_avail(1, 2)], [_avail(0, 4)]), [])
        self.assertEqual(Availability.difference([], [_avail(0, 4)]), [])
