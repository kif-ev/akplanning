from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from AKModel.models import AK, AKSlot, Event


class SlotDurationTests(TestCase):
    """
    Tests for the restrictions of slot durations (positive, never longer than the event)
    """
    fixtures = ['model.json']

    def setUp(self):
        # kif42 lasts four days (+ one second), i.e., 96 hours
        self.event = Event.get_by_slug('kif42')
        self.ak = AK.objects.get(pk=1)

    def test_max_slot_duration(self):
        """
        Test that the maximum slot duration is the event length, rounded down to the precision of the field
        and never more than can be stored in the duration field
        """
        self.assertEqual(self.event.max_slot_duration, Decimal("96.00"))

        self.event.end = self.event.start + timedelta(hours=3, minutes=20)
        self.assertEqual(self.event.max_slot_duration, Decimal("3.33"))

        self.event.end = self.event.start + timedelta(days=10)
        self.assertEqual(self.event.max_slot_duration, Decimal("99.99"))

    def test_save_clamps_duration(self):
        """
        Test that saving a slot clamps its duration to the event length (without rounding to whole hours)
        """
        slot = AKSlot.objects.create(ak=self.ak, event=self.event, duration=Decimal("97"))
        self.assertEqual(AKSlot.objects.get(pk=slot.pk).duration, Decimal("96"))

        slot = AKSlot.objects.create(ak=self.ak, event=self.event, duration=Decimal("1.5"))
        self.assertEqual(AKSlot.objects.get(pk=slot.pk).duration, Decimal("1.5"))

        self.event.end = self.event.start + timedelta(hours=1, minutes=30)
        self.event.save()
        slot = AKSlot.objects.create(ak=self.ak, event=self.event, duration=Decimal("2"))
        self.assertEqual(AKSlot.objects.get(pk=slot.pk).duration, Decimal("1.5"))

    def test_clean_rejects_non_positive_duration(self):
        """
        Test that slots without a positive duration are rejected
        """
        for duration in ["0", "-1"]:
            slot = AKSlot(ak=self.ak, event=self.event, duration=Decimal(duration))
            with self.assertRaises(ValidationError, msg=f"Duration {duration} was accepted"):
                slot.full_clean()
