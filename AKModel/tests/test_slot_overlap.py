from datetime import timedelta
from decimal import Decimal
from django.test import TestCase

from AKModel.models import AK, AKSlot, Event


class SlotOverlapTests(TestCase):
    """
    Tests for the computation of slot end times and the overlap check of slots
    """
    fixtures = ['model.json']

    def setUp(self):
        self.event = Event.get_by_slug('kif42')
        self.ak = AK.objects.get(pk=1)

    def _slot(self, start_offset_minutes, duration):
        return AKSlot(ak=self.ak, event=self.event,
                      start=self.event.start + timedelta(minutes=start_offset_minutes), duration=Decimal(duration))

    def test_end_rounded_to_full_minutes(self):
        """
        Test that durations not exactly representable with two decimal places result in the intended end time
        """
        for duration, minutes in [("0.17", 10), ("0.33", 20), ("0.67", 40), ("0.83", 50), ("1.67", 100),
                                  ("1.5", 90), ("2", 120)]:
            slot = self._slot(0, duration)
            self.assertEqual(slot.end - slot.start, timedelta(minutes=minutes), msg=f"Duration {duration}")

    def test_adjacent_slots_do_not_overlap(self):
        """
        Test that slots directly following each other are not considered overlapping
        """
        for duration in ["0.17", "0.33", "0.67", "1", "1.67"]:
            first = self._slot(0, duration)
            second = self._slot(round(float(duration) * 60), "1")
            self.assertFalse(first.overlaps(second), msg=f"Duration {duration}")
            self.assertFalse(second.overlaps(first), msg=f"Duration {duration}")

    def test_overlap_symmetric(self):
        """
        Test that overlaps are detected independent of the order of the slots (including containment)
        """
        cases = [
            (self._slot(0, "3"), self._slot(60, "1")),  # containment
            (self._slot(0, "2"), self._slot(60, "2")),  # partial overlap
            (self._slot(0, "1"), self._slot(0, "1")),  # identical
            (self._slot(0, "1"), self._slot(0, "2")),  # same start
            (self._slot(0, "2"), self._slot(60, "1")),  # same end
        ]
        for a, b in cases:
            self.assertTrue(a.overlaps(b))
            self.assertTrue(b.overlaps(a))

    def test_separate_slots_do_not_overlap(self):
        """
        Test that slots with a gap between them are not considered overlapping
        """
        a, b = self._slot(0, "1"), self._slot(90, "1")
        self.assertFalse(a.overlaps(b))
        self.assertFalse(b.overlaps(a))

    def test_unscheduled_slot(self):
        """
        Test that unscheduled slots have no end and that the scheduled times are rejected for them
        """
        slot = AKSlot(ak=self.ak, event=self.event, duration=Decimal("1"))
        self.assertIsNone(slot.end)
        with self.assertRaises(ValueError):
            _ = slot.scheduled_start
        with self.assertRaises(ValueError):
            _ = slot.scheduled_end
        with self.assertRaises(ValueError):
            slot.overlaps(self._slot(0, "1"))
