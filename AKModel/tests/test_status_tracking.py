from datetime import datetime, timedelta, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from AKModel.models import Event, StatusTrackingEntry
from AKModel.status_tracking import StatusTracker, status_tracker

Progress = StatusTrackingEntry.Progress


class StatusTrackerRegistrationTests(TestCase):
    """
    Tests for registering phases and steps
    """

    def setUp(self):
        self.tracker = StatusTracker()

    def test_ordering(self):
        """
        Test that phases and steps are returned ordered, independent of registration order
        """
        self.tracker.register_step("b", "s2", "Step 2", order=2)
        self.tracker.register_phase("b", "Phase B", order=2)
        self.tracker.register_phase("a", "Phase A", order=1)
        self.tracker.register_step("b", "s1", "Step 1", order=1)
        self.tracker.register_step("a", "s3", "Step 3")

        self.assertEqual([p.key for p in self.tracker.get_phases()], ["a", "b"])
        self.assertEqual([(s.phase, s.key) for s in self.tracker.get_steps()], [("a", "s3"), ("b", "s1"), ("b", "s2")])
        self.assertEqual([s.key for s in self.tracker.get_steps("b")], ["s1", "s2"])

    def test_steps_of_unregistered_phase_are_ignored(self):
        """
        Test that steps are only listed once their phase is registered
        """
        self.tracker.register_step("later", "s", "Step")
        self.assertEqual(self.tracker.get_steps(), [])
        with self.assertRaises(KeyError):
            self.tracker.get_steps("later")
        self.tracker.register_phase("later", "Later")
        self.assertEqual(len(self.tracker.get_steps()), 1)

    def test_invalid_registrations(self):
        """
        Test that duplicate or invalid keys are rejected
        """
        self.tracker.register_phase("p", "Phase")
        self.tracker.register_step("p", "s", "Step")
        with self.assertRaises(ValueError):
            self.tracker.register_phase("p", "Phase again")
        with self.assertRaises(ValueError):
            self.tracker.register_step("p", "s", "Step again")
        with self.assertRaises(ValueError):
            self.tracker.register_phase("with space", "Invalid")
        # Same step key in a different phase is fine
        self.tracker.register_step("q", "s", "Step")

    def test_default_registrations(self):
        """
        Test that the apps registered their phases and steps with the global tracker
        """
        self.assertEqual([p.key for p in status_tracker.get_phases()],
                         ["configuration", "scheduling", "aftermath"])
        self.assertIn("rooms", [s.key for s in status_tracker.get_steps("scheduling")])
        self.assertIn("wiki_export", [s.key for s in status_tracker.get_steps("aftermath")])


class StatusTrackerProgressTests(TestCase):
    """
    Tests for recording and querying progress
    """
    fixtures = ['model.json']

    def setUp(self):
        self.event = Event.get_by_slug('kif42')
        self.other_event = Event.objects.exclude(pk=self.event.pk).first()
        self.tracker = StatusTracker()
        self.tracker.register_phase("p1", "Phase 1", order=1)
        self.tracker.register_phase("p2", "Phase 2", order=2)
        self.tracker.register_phase("empty", "Empty phase", order=3)
        for i in range(1, 5):
            self.tracker.register_step("p1", f"s{i}", f"Step {i}", order=i)
        self.tracker.register_step("p2", "s1", "Step 1 of phase 2")

    def test_no_entries_means_not_started(self):
        """
        Test that steps without entries are reported as not started, without creating entries
        """
        statuses = self.tracker.get_progress(self.event)
        self.assertEqual(len(statuses), 5)
        for status in statuses:
            self.assertEqual(status.progress, Progress.NOT_STARTED)
            self.assertIsNone(status.entry)
            self.assertIsNone(status.timestamp)
            self.assertEqual(status.detail, "")
        self.assertFalse(StatusTrackingEntry.objects.exists())

    def test_latest_entry_wins(self):
        """
        Test that multiple increments can be stored and the most recent one determines the progress
        """
        self.tracker.record(self.event, "p1", "s1", Progress.IN_PROGRESS, detail="Started")
        self.tracker.record(self.event, "p1", "s1", Progress.FAILED, detail="Oops")
        self.tracker.record(self.event, "p1", "s1", Progress.DONE, detail="Finally")
        # Entry with an older timestamp recorded later must not override the newer ones
        StatusTrackingEntry.objects.create(event=self.event, phase="p1", step="s1", progress=Progress.FAILED,
                                           timestamp=timezone.now() - timedelta(days=1))
        # Entries of other events or steps must not interfere
        if self.other_event is not None:
            self.tracker.record(self.other_event, "p1", "s1", Progress.FAILED)
        self.tracker.record(self.event, "p2", "s1", Progress.FAILED)

        status = self.tracker.get_phase_progress(self.event, "p1")[0]
        self.assertEqual(status.step.key, "s1")
        self.assertEqual(status.progress, Progress.DONE)
        self.assertEqual(status.detail, "Finally")
        self.assertEqual(self.tracker.get_history(self.event, "p1", "s1").count(), 4)
        self.assertEqual(self.tracker.get_phase_progress(self.event, "p2")[0].progress, Progress.FAILED)

    def test_query_count(self):
        """
        Test that the progress of all steps is retrieved with a single query
        """
        for i in range(1, 5):
            self.tracker.record(self.event, "p1", f"s{i}", Progress.IN_PROGRESS)
            self.tracker.record(self.event, "p1", f"s{i}", Progress.DONE)
        with self.assertNumQueries(1):
            statuses = self.tracker.get_progress(self.event)
            self.assertEqual([s.progress for s in statuses], [Progress.DONE] * 4 + [Progress.NOT_STARTED])

    def test_record_validation(self):
        """
        Test that progress can only be recorded for registered steps and with valid progress values
        """
        with self.assertRaises(KeyError):
            self.tracker.record(self.event, "p1", "unknown", Progress.DONE)
        with self.assertRaises(KeyError):
            self.tracker.record(self.event, "unknown", "s1", Progress.DONE)
        with self.assertRaises(ValueError):
            self.tracker.record(self.event, "p1", "s1", "almost_done")

    def test_entries_of_unregistered_steps_are_ignored(self):
        """
        Test that entries of steps that are no longer registered do not show up
        """
        StatusTrackingEntry.objects.create(event=self.event, phase="p1", step="removed", progress=Progress.DONE)
        self.assertEqual(len(self.tracker.get_phase_progress(self.event, "p1")), 4)
        self.assertEqual(self.tracker.get_phase_fractions(self.event, "p1")[Progress.DONE], 0.0)

    def test_phase_fractions(self):
        """
        Test computation of fractions per progress for a phase
        """
        self.tracker.record(self.event, "p1", "s1", Progress.DONE)
        self.tracker.record(self.event, "p1", "s2", Progress.DONE)
        self.tracker.record(self.event, "p1", "s3", Progress.IN_PROGRESS)
        self.tracker.record(self.event, "p1", "s3", Progress.FAILED)

        fractions = self.tracker.get_phase_fractions(self.event, "p1")
        self.assertEqual(fractions, {
            Progress.NOT_STARTED: 0.25,
            Progress.IN_PROGRESS: 0.0,
            Progress.FAILED: 0.25,
            Progress.DONE: 0.5,
        })
        self.assertEqual(self.tracker.get_phase_fractions(self.event, "empty"), {p: 0.0 for p in Progress})

    def test_missing_mandatory(self):
        """
        Test that the access methods report the number of mandatory steps that are not done yet
        """
        self.tracker.register_step("p2", "m1", "Mandatory 1", mandatory=True)
        self.tracker.register_step("p2", "m2", "Mandatory 2", mandatory=True)
        self.tracker.register_step("p2", "m3", "Mandatory 3", mandatory=True)
        self.tracker.register_step("empty_mandatory", "m", "Mandatory of unregistered phase", mandatory=True)

        # Nothing done yet: all mandatory steps are missing, optional ones are never counted
        self.assertEqual(self.tracker.get_progress(self.event).missing_mandatory, 3)
        self.assertEqual(self.tracker.get_phase_progress(self.event, "p1").missing_mandatory, 0)
        self.assertEqual(self.tracker.get_phase_fractions(self.event, "p2").missing_mandatory, 3)
        self.assertEqual(self.tracker.get_phase_fractions(self.event, "empty").missing_mandatory, 0)

        # Only done steps count as no longer missing (in progress and failed ones are still missing)
        self.tracker.record(self.event, "p2", "m1", Progress.DONE)
        self.tracker.record(self.event, "p2", "m2", Progress.IN_PROGRESS)
        self.tracker.record(self.event, "p2", "m3", Progress.FAILED)
        self.tracker.record(self.event, "p2", "s1", Progress.DONE)
        report = self.tracker.get_phase_progress(self.event, "p2")
        self.assertEqual(report.missing_mandatory, 2)
        self.assertEqual([s.step.key for s in report.missing_mandatory_steps], ["m2", "m3"])
        self.assertEqual(self.tracker.get_progress(self.event).missing_mandatory, 2)
        self.assertEqual(self.tracker.get_phase_fractions(self.event, "p2").missing_mandatory, 2)

        # Done steps that are reopened are missing again
        self.tracker.record(self.event, "p2", "m1", Progress.IN_PROGRESS)
        self.assertEqual(self.tracker.get_phase_fractions(self.event, "p2").missing_mandatory, 3)


class StatusTrackingAdminTests(TestCase):
    """
    Tests for the admin interface of status tracking entries
    """
    fixtures = ['model.json']

    def setUp(self):
        self.event = Event.get_by_slug('kif42')
        self.admin_user = get_user_model().objects.create(username="statusadmin", is_staff=True,
                                                          is_superuser=True, is_active=True)
        self.client.force_login(self.admin_user)

    def test_views(self):
        """
        Test that list, add and change views (also for entries of unregistered steps) work
        """
        known = status_tracker.record(self.event, "scheduling", "rooms", Progress.DONE, detail="All rooms")
        unknown = StatusTrackingEntry.objects.create(event=self.event, phase="gone", step="removed")

        response = self.client.get(reverse("admin:AKModel_statustrackingentry_changelist"))
        self.assertContains(response, "Create rooms")
        self.assertContains(response, "removed")
        # Mandatory column: yes for rooms, unknown for the unregistered step
        self.assertContains(response, 'class="field-mandatory_display"><img src="/static/admin/img/icon-yes.svg"')
        self.assertContains(response, 'class="field-mandatory_display"><img src="/static/admin/img/icon-unknown.svg"')
        response = self.client.get(reverse("admin:AKModel_statustrackingentry_changelist"), {"phase": "scheduling"})
        self.assertNotContains(response, "removed")

        response = self.client.get(reverse("admin:AKModel_statustrackingentry_add"))
        # Mandatory steps are marked in the selection, optional ones are not
        self.assertContains(response, ">Create rooms *</option>")
        self.assertContains(response, ">Transfer AK list to wiki</option>")
        for entry in [known, unknown]:
            response = self.client.get(reverse("admin:AKModel_statustrackingentry_change", args=[entry.pk]))
            self.assertContains(response, f'value="{entry.phase}/{entry.step}" selected')

    def test_create(self):
        """
        Test that creating an entry via the admin stores phase and step correctly
        """
        now = timezone.localtime(timezone.now())
        response = self.client.post(reverse("admin:AKModel_statustrackingentry_add"), {
            "event": self.event.pk,
            "phase_step": "aftermath/wiki_export",
            "progress": Progress.IN_PROGRESS,
            "detail": "Half done",
            "timestamp_0": now.strftime("%Y-%m-%d"),
            "timestamp_1": now.strftime("%H:%M:%S"),
        })
        self.assertEqual(response.status_code, 302)
        entry = StatusTrackingEntry.objects.get()
        self.assertEqual((entry.phase, entry.step, entry.progress), ("aftermath", "wiki_export", "in_progress"))

        response = self.client.post(reverse("admin:AKModel_statustrackingentry_add"), {
            "event": self.event.pk, "phase_step": "aftermath/unknown", "progress": Progress.DONE,
            "timestamp_0": now.strftime("%Y-%m-%d"), "timestamp_1": now.strftime("%H:%M:%S"),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(StatusTrackingEntry.objects.count(), 1)

    def test_event_timezone(self):
        """
        Test that timestamps are displayed and edited in the timezone of the event (Europe/Berlin, UTC+1 in winter)
        """
        entry = StatusTrackingEntry.objects.create(
            event=self.event, phase="scheduling", step="rooms", progress=Progress.DONE,
            timestamp=datetime(2026, 1, 15, 12, 0, tzinfo=dt_timezone.utc))

        response = self.client.get(reverse("admin:AKModel_statustrackingentry_changelist"))
        self.assertContains(response, "13:00")
        response = self.client.get(reverse("admin:AKModel_statustrackingentry_change", args=[entry.pk]))
        self.assertContains(response, 'value="13:00:00"')

        response = self.client.post(reverse("admin:AKModel_statustrackingentry_change", args=[entry.pk]), {
            "event": self.event.pk, "phase_step": "scheduling/rooms", "progress": Progress.DONE,
            "timestamp_0": "2026-01-15", "timestamp_1": "14:30:00",
        })
        self.assertEqual(response.status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.timestamp, datetime(2026, 1, 15, 13, 30, tzinfo=dt_timezone.utc))
