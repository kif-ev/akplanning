from datetime import timedelta

from django.test import TestCase

from AKModel.availability.models import Availability
from AKModel.models import AK, Event
from AKPreference.models import AKPreference, EventParticipant
from AKSolverInterface.checks import participants_required_for_too_many_slots, required_preferences_without_overlap
from AKSolverInterface.lookup import lookup_participants


class TrashedAKChecksTest(TestCase):
    """
    Trashed AKs (and preferences for them) should be ignored by the checks of the automatic scheduling workflow
    """
    fixtures = ["model.json"]

    def setUp(self):
        self.event = Event.objects.get(pk=2)
        self.participant = EventParticipant.objects.create(name="Tester", event=self.event)
        self.active_ak = AK.objects.get(pk=1)
        self.trashed_ak = AK.objects.get(pk=3)
        for ak in (self.active_ak, self.trashed_ak):
            AKPreference.objects.create(event=self.event, participant=self.participant, ak=ak,
                                        preference=AKPreference.PreferenceLevel.REQUIRED)
        self.trashed_ak.move_to_trash()

    def test_overlap_check_ignores_trashed(self):
        loose, strict = required_preferences_without_overlap(self.event)
        for violations in (loose, strict or []):
            self.assertNotIn(self.trashed_ak.pk, [v["preference"].ak.pk for v in violations])
        # Sanity check: the AK has no availabilities, hence it is reported when not trashed
        self.trashed_ak.restore_from_trash()
        loose, _ = required_preferences_without_overlap(self.event)
        self.assertIn(self.trashed_ak.pk, [v["preference"].ak.pk for v in loose])

    def test_too_many_slots_check_ignores_trashed(self):
        for violation in participants_required_for_too_many_slots(self.event):
            self.assertNotIn(self.trashed_ak.pk, [p.ak.pk for p in violation["preferences"]])

    def test_export_ignores_trashed(self):
        # Participant with restricted availability, only required for the trashed AK
        AKPreference.objects.filter(participant=self.participant, ak=self.active_ak).delete()
        Availability.objects.create(event=self.event, participant=self.participant,
                                    start=self.event.start, end=self.event.start + timedelta(hours=1))
        self.assertEqual(self.participant.get_time_constraints(), [])
        self.assertFalse(self.participant.export_preferences.exists())

        self.trashed_ak.restore_from_trash()
        self.assertEqual(self.participant.get_time_constraints(), [f"availability-participant-{self.participant.pk}"])
        self.assertTrue(self.participant.export_preferences.exists())

    def test_lookup_ignores_trashed(self):
        fields = dict(lookup_participants(self.event)[str(self.participant.pk)]["fields"])
        self.assertEqual(fields["Preferences"], "1")
        self.assertEqual([ref["id"] for ref in fields["Required for"]], [str(self.active_ak.pk)])
