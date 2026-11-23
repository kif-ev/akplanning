from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from AKModel.models import AK, Event
from AKModel.tests.test_views import BasicViewTests
from AKPreference.models import AKPreference, EventParticipant
from AKPreference.views import uuid_key


class PollViewTests(BasicViewTests, TestCase):
    """
    Tests for AKPreference Poll
    """
    fixtures = ['model.json']
    APP_NAME = 'poll'

    def test_poll_redirect(self):
        """
        Test: Make sure that user is redirected from poll to dashboard when poll is hidden
        """
        event = Event.objects.get(slug='kif42')
        _, url_poll = self._name_and_url(('start', {'event_slug': event.slug}))
        url_dashboard = reverse("dashboard:dashboard_event", kwargs={"slug": event.slug})

        event.poll_hidden = True
        event.save()

        self.client.logout()
        response = self.client.get(url_poll)

        self.assertRedirects(response, url_dashboard,
                             msg_prefix=f"Redirect away from poll not working ({url_poll} -> {url_dashboard})")

        self.client.force_login(self.staff_user)
        response = self.client.get(url_poll)

        self.assertEqual(
                response.status_code,
                200,
                msg=f"{url_poll} broken",
        )

        self.assertTemplateUsed(response, "AKPreference/poll_start.html",
                                msg_prefix="Poll is not visible for staff user")


class EnterPreferencesTrashedAKTests(TestCase):
    """
    Tests for entering preferences when AKs are moved to the trash
    """
    fixtures = ['model.json']

    def setUp(self):
        self.event = Event.objects.get(slug='kif42')
        self.event.poll_hidden = False
        self.event.save()
        self.participant = EventParticipant.objects.create(event=self.event, name="Participant")
        session = self.client.session
        session[uuid_key(self.event)] = str(self.participant.uuid)
        session.save()
        # Category 4 contains AKs 1 and 4
        self.url = reverse('poll:preferences-enter', kwargs={'event_slug': self.event.slug, 'category_pk': 4})

    def _post_data(self, rows, initial_forms=0):
        """
        Build the POST data of the formset, each row is a tuple (preference id or None, AK id, preference level)
        """
        data = {
            'form-TOTAL_FORMS': str(len(rows)),
            'form-INITIAL_FORMS': str(initial_forms),
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
        }
        for i, (pref_id, ak_id, preference) in enumerate(rows):
            data.update({
                f'form-{i}-event': self.event.pk,
                f'form-{i}-participant': self.participant.pk,
                f'form-{i}-ak': ak_id,
                f'form-{i}-preference': preference,
            })
            if pref_id is not None:
                data[f'form-{i}-id'] = pref_id
        return data

    def test_saved_preference_for_trashed_ak(self):
        """
        Test: The form can still be displayed when an AK with a saved preference was trashed
        """
        AKPreference.objects.create(event=self.event, participant=self.participant, ak_id=1, preference=2)
        AK.objects.get(pk=1).move_to_trash()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([f.ak_obj.pk for f in response.context['form']], [4])

    def test_submit_after_ak_was_trashed(self):
        """
        Test: Submitting the form after an AK was trashed saves the remaining preferences
        """
        AK.objects.get(pk=1).move_to_trash()

        response = self.client.post(self.url, self._post_data([(None, 1, 3), (None, 4, 2)]))
        self.assertRedirects(response, reverse('poll:overview', kwargs={'event_slug': self.event.slug}))
        self.assertEqual(list(self.participant.akpreference_set.values_list('ak', 'preference')), [(4, 2)])
        self.assertIn("Some AKs were removed in the meantime. Your preferences for them were not saved.",
                      [str(m) for m in get_messages(response.wsgi_request)])

    def test_submit_ignore_after_ak_was_trashed(self):
        """
        Test: Submitting "ignore" for a new preference after an AK was trashed does not fail
        """
        AK.objects.get(pk=1).move_to_trash()

        response = self.client.post(self.url, self._post_data([(None, 1, 3), (None, 4, 0)]))
        self.assertRedirects(response, reverse('poll:overview', kwargs={'event_slug': self.event.slug}))
        self.assertFalse(self.participant.akpreference_set.exists())

    def test_invalid_submit_after_ak_was_trashed(self):
        """
        Test: An invalid submission after an AK with a saved preference was trashed is displayed again
        with the correct AKs
        """
        pref = AKPreference.objects.create(event=self.event, participant=self.participant, ak_id=1, preference=2)
        AK.objects.get(pk=1).move_to_trash()

        response = self.client.post(self.url, self._post_data([(pref.pk, 1, 2), (None, 4, 99)], initial_forms=1))
        self.assertEqual(response.status_code, 200)
        forms = [f for f in response.context['form'] if not f.stale]
        self.assertEqual([f.ak_obj.pk for f in forms], [4])
        self.assertIn('preference', forms[0].errors)
        self.assertEqual(AKPreference.objects.get(pk=pref.pk).preference, 2)

    def test_resubmit_after_invalid_submit_with_trashed_ak(self):
        """
        Test: Resubmitting a form that was re-displayed without the rows of trashed AKs
        saves the preferences and does not warn about the removed AKs again
        """
        AK.objects.get(pk=1).move_to_trash()
        self.client.post(self.url, self._post_data([(None, 1, 3), (None, 4, 99)]))

        # The row for the trashed AK is not rendered again, but still counted in the management form
        data = self._post_data([(None, 1, 3), (None, 4, 2)])
        data = {k: v for k, v in data.items() if not k.startswith('form-0-')}
        response = self.client.post(self.url, data)
        self.assertRedirects(response, reverse('poll:overview', kwargs={'event_slug': self.event.slug}))
        self.assertEqual(list(self.participant.akpreference_set.values_list('ak', 'preference')), [(4, 2)])
        self.assertNotIn("Some AKs were removed in the meantime. Your preferences for them were not saved.",
                         [str(m) for m in get_messages(response.wsgi_request)])
