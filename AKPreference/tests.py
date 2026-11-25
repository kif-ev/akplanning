from datetime import timedelta

from django.contrib import admin
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.urls import reverse

from AKModel.availability.models import Availability
from AKModel.models import AK, AKOwner, AKRequirement, Event
from AKModel.tests.test_views import BasicViewTests
from AKPreference.admin import EventParticipantAdmin
from AKPreference.forms import EventParticipantForm
from AKPreference.models import AKPreference, EventParticipant
from AKPreference.views import uuid_key
from AKSolverInterface.lookup import lookup_participants
from AKSolverInterface.serializers import ExportEventSerializer


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

    def test_submit_for_other_participant(self):
        """
        Test: Changing the submitted participant does not save preferences for another participant
        """
        other = EventParticipant.objects.create(event=self.event, name="Other")
        data = self._post_data([(None, 1, 2), (None, 4, 1)])
        data['form-0-participant'] = other.pk

        response = self.client.post(self.url, data)
        self.assertRedirects(response, reverse('poll:overview', kwargs={'event_slug': self.event.slug}))
        self.assertFalse(other.akpreference_set.exists())
        self.assertCountEqual(self.participant.akpreference_set.values_list('ak', 'preference'), [(1, 2), (4, 1)])

    def test_submit_existing_preference_of_other_participant(self):
        """
        Test: Submitting the id of a preference of another participant does not change it
        (the row is treated as a new preference of the participant instead)
        """
        other = EventParticipant.objects.create(event=self.event, name="Other")
        pref = AKPreference.objects.create(event=self.event, participant=other, ak_id=1, preference=1)

        response = self.client.post(self.url, self._post_data([(pref.pk, 1, 2)], initial_forms=1))
        self.assertRedirects(response, reverse('poll:overview', kwargs={'event_slug': self.event.slug}))
        pref.refresh_from_db()
        self.assertEqual((pref.participant, pref.preference), (other, 1))
        self.assertEqual(list(self.participant.akpreference_set.values_list('ak', 'preference')), [(1, 2)])

    def test_submit_after_ak_was_trashed(self):
        """
        Test: Submitting the form after an AK was trashed saves the remaining preferences
        """
        AK.objects.get(pk=1).move_to_trash()

        response = self.client.post(self.url, self._post_data([(None, 1, 2), (None, 4, 2)]))
        self.assertRedirects(response, reverse('poll:overview', kwargs={'event_slug': self.event.slug}))
        self.assertEqual(list(self.participant.akpreference_set.values_list('ak', 'preference')), [(4, 2)])
        self.assertIn("Some AKs were removed in the meantime. Your preferences for them were not saved.",
                      [str(m) for m in get_messages(response.wsgi_request)])

    def test_submit_ignore_after_ak_was_trashed(self):
        """
        Test: Submitting "ignore" for a new preference after an AK was trashed does not fail
        """
        AK.objects.get(pk=1).move_to_trash()

        response = self.client.post(self.url, self._post_data([(None, 1, 2), (None, 4, 0)]))
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
        self.client.post(self.url, self._post_data([(None, 1, 2), (None, 4, 99)]))

        # The row for the trashed AK is not rendered again, but still counted in the management form
        data = self._post_data([(None, 1, 2), (None, 4, 2)])
        data = {k: v for k, v in data.items() if not k.startswith('form-0-')}
        response = self.client.post(self.url, data)
        self.assertRedirects(response, reverse('poll:overview', kwargs={'event_slug': self.event.slug}))
        self.assertEqual(list(self.participant.akpreference_set.values_list('ak', 'preference')), [(4, 2)])
        self.assertNotIn("Some AKs were removed in the meantime. Your preferences for them were not saved.",
                         [str(m) for m in get_messages(response.wsgi_request)])


class ParticipantAKOwnerTests(TestCase):
    """
    Tests for linking participants to AK owners
    """
    fixtures = ['model.json']

    def setUp(self):
        self.event = Event.objects.get(slug='kif42')

    def test_form_ak_owner_optional_and_restricted_to_event(self):
        """
        Test: The AK owner field is optional and only offers the AK owners of the event
        """
        form = EventParticipantForm(initial={'event': self.event})
        self.assertFalse(form.fields['ak_owner'].required)
        self.assertCountEqual(form.fields['ak_owner'].queryset, AKOwner.objects.filter(event=self.event))

    def test_form_without_ak_owners(self):
        """
        Test: The AK owner field is not shown if the event has no AK owners
        """
        AKOwner.objects.filter(event=self.event).delete()
        form = EventParticipantForm(initial={'event': self.event})
        self.assertNotIn('ak_owner', form.fields)

    def test_export_linked_owner(self):
        """
        Test: A participant linked to an AK owner is required for all slots of the AKs of that owner
        (replacing their own preferences for these AKs) and no dummy participant is exported for that owner
        """
        owner = AKOwner.objects.get(pk=1)  # owns AKs 1 and 4
        participant = EventParticipant.objects.create(event=self.event, name="Owner", ak_owner=owner)
        requirement = AKRequirement.objects.filter(event=self.event).first()
        participant.requirements.add(requirement)
        AKPreference.objects.create(event=self.event, participant=participant, ak_id=1, preference=2)
        AKPreference.objects.create(event=self.event, participant=participant, ak_id=2, preference=1)

        export = ExportEventSerializer(self.event).data
        exported = next(p for p in export['participants'] if p['id'] == participant.pk)
        expected = [{'ak_id': 2, 'required': False, 'preference_score': 1}] + [
            {'ak_id': slot_pk, 'required': True, 'preference_score': -1} for slot_pk in [1, 5, 6, 7, 8]
        ]
        self.assertCountEqual(exported['preferences'], expected)
        self.assertEqual(exported['time_constraints'], [])
        # room constraints are kept, e.g. for accessibility needs
        self.assertEqual(exported['room_constraints'], [requirement.name])

        dummy_names = [p['info']['name'] for p in export['participants'] if p['id'] != participant.pk]
        self.assertNotIn(f"{owner} [AKOwner]", dummy_names)
        self.assertIn(f"{AKOwner.objects.get(pk=2)} [AKOwner]", dummy_names)

    def test_ak_owner_must_belong_to_event(self):
        """
        Test: A participant cannot be linked to an AK owner of another event
        """
        other_owner = AKOwner.objects.exclude(event=self.event).first()
        participant = EventParticipant(event=self.event, name="Owner", ak_owner=other_owner)
        with self.assertRaises(ValidationError) as context:
            participant.full_clean()
        self.assertIn('ak_owner', context.exception.message_dict)

        participant.ak_owner = AKOwner.objects.get(pk=1)
        participant.full_clean()

    def test_poll_owned_aks_not_rated(self):
        """
        Test: AKs owned by a linked participant are shown as their own AKs in the poll and cannot be rated
        """
        self.event.poll_hidden = False
        self.event.save()
        participant = EventParticipant.objects.create(event=self.event, name="Owner",
                                                      ak_owner=AKOwner.objects.get(pk=1))
        session = self.client.session
        session[uuid_key(self.event)] = str(participant.uuid)
        session.save()
        # Category 4 contains AKs 1 and 4, both owned by AK owner 1
        url = reverse('poll:preferences-enter', kwargs={'event_slug': self.event.slug, 'category_pk': 4})

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['form'].forms), 0)
        self.assertCountEqual([ak.pk for ak in response.context['owned_aks']], [1, 4])
        self.assertContains(response, "Your AK")

        # Submitted preferences for owned AKs are not saved
        response = self.client.post(url, {
            'form-TOTAL_FORMS': '1', 'form-INITIAL_FORMS': '0', 'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000', 'form-0-event': self.event.pk, 'form-0-participant': participant.pk,
            'form-0-ak': 1, 'form-0-preference': 2,
        })
        self.assertRedirects(response, reverse('poll:overview', kwargs={'event_slug': self.event.slug}))
        self.assertFalse(participant.akpreference_set.exists())
        # The AK was not removed, the participant is responsible for it (e.g., linked in another tab)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertIn("You are responsible for some AKs by now. Your preferences for them were not saved.", messages)
        self.assertNotIn("Some AKs were removed in the meantime. Your preferences for them were not saved.", messages)

    def test_preferences_for_owned_aks_not_counted(self):
        """
        Test: Preferences saved before linking the participant to the owner of the AK are kept,
        but neither counted in the poll overview, the admin, nor the lookup
        """
        self.event.poll_hidden = False
        self.event.save()
        participant = EventParticipant.objects.create(event=self.event, name="Owner")
        # Category 4 contains AKs 1 and 4, both owned by AK owner 1
        AKPreference.objects.create(event=self.event, participant=participant, ak_id=1, preference=2)
        participant.ak_owner = AKOwner.objects.get(pk=1)
        participant.save()
        session = self.client.session
        session[uuid_key(self.event)] = str(participant.uuid)
        session.save()

        response = self.client.get(reverse('poll:overview', kwargs={'event_slug': self.event.slug}))
        category = next(c for c in response.context['categories'] if c.pk == 4)
        self.assertFalse(category.has_saved_preferences)

        model_admin = EventParticipantAdmin(EventParticipant, admin.site)
        self.assertEqual(model_admin.get_queryset(RequestFactory().get('/')).get(pk=participant.pk).preference_count,
                         0)
        self.assertIn(['Preferences', '0'], lookup_participants(self.event)[str(participant.pk)]['fields'])
        self.assertTrue(participant.akpreference_set.exists())

    def test_dummy_ids_match_lookup_without_preferences(self):
        """
        Test: Without exporting preferences, a dummy participant is exported for a linked owner,
        and its id can be resolved by the lookup
        """
        owner = AKOwner.objects.get(pk=1)
        EventParticipant.objects.create(event=self.event, name="Owner", ak_owner=owner)

        export = ExportEventSerializer(self.event, export_preferences=False).data
        lookup = lookup_participants(self.event)
        dummy = next(p for p in export['participants'] if p['info']['name'] == f"{owner} [AKOwner]")
        self.assertIn(str(dummy['id']), lookup)
        self.assertIn(str(owner), str(lookup[str(dummy['id'])]['title']))
        for participant in export['participants']:
            self.assertIn(str(participant['id']), lookup)


class RequiredPreferenceTests(TestCase):
    """
    Tests for the preference level 'Required', which can no longer be selected but is kept for existing preferences
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

    def _post(self, rows, initial_forms=0):
        """
        Submit the formset, each row is a tuple (preference id or None, AK id, preference level)
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
        return self.client.post(self.url, data)

    @staticmethod
    def _choices(form) -> list[int]:
        return [value for value, _label in form.fields['preference'].choices]

    def test_required_only_offered_for_existing_required_preferences(self):
        """
        Test: 'Required' is only offered for rows whose saved preference already is 'Required'
        """
        AKPreference.objects.create(event=self.event, participant=self.participant, ak_id=1,
                                    preference=AKPreference.PreferenceLevel.REQUIRED)

        response = self.client.get(self.url)
        choices = {f.ak_obj.pk: self._choices(f) for f in response.context['form']}
        self.assertIn(AKPreference.PreferenceLevel.REQUIRED, choices[1])
        self.assertNotIn(AKPreference.PreferenceLevel.REQUIRED, choices[4])

    def test_existing_required_preference_kept(self):
        """
        Test: Saving the preferences again keeps an existing 'Required' preference
        """
        pref = AKPreference.objects.create(event=self.event, participant=self.participant, ak_id=1,
                                           preference=AKPreference.PreferenceLevel.REQUIRED)

        response = self._post([(pref.pk, 1, 3), (None, 4, 1)], initial_forms=1)
        self.assertRedirects(response, reverse('poll:overview', kwargs={'event_slug': self.event.slug}))
        pref.refresh_from_db()
        self.assertEqual(pref.preference, AKPreference.PreferenceLevel.REQUIRED)

    def test_required_cannot_be_selected(self):
        """
        Test: 'Required' cannot be selected for new preferences or preferences with another level
        """
        pref = AKPreference.objects.create(event=self.event, participant=self.participant, ak_id=1, preference=2)

        response = self._post([(pref.pk, 1, 3), (None, 4, 3)], initial_forms=1)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all('preference' in f.errors for f in response.context['form']))
        pref.refresh_from_db()
        self.assertEqual(pref.preference, 2)
        self.assertFalse(self.participant.akpreference_set.filter(ak_id=4).exists())

    def test_export_required_preference(self):
        """
        Test: Existing 'Required' preferences are exported as hard constraints,
        including the availabilities of the participant
        """
        AKPreference.objects.create(event=self.event, participant=self.participant, ak_id=1,
                                    preference=AKPreference.PreferenceLevel.REQUIRED)
        Availability.objects.create(event=self.event, participant=self.participant, start=self.event.start,
                                    end=self.event.start + timedelta(days=1))

        export = ExportEventSerializer(self.event).data
        exported = next(p for p in export['participants'] if p['id'] == self.participant.pk)
        self.assertCountEqual(exported['preferences'], [
            {'ak_id': slot_pk, 'required': True, 'preference_score': -1}
            for slot_pk in AK.objects.get(pk=1).akslot_set.values_list('pk', flat=True)
        ])
        constraint = f"availability-participant-{self.participant.pk}"
        self.assertEqual(exported['time_constraints'], [constraint])
        self.assertTrue(any(constraint in timeslot['fulfilled_time_constraints']
                            for block in export['timeslots']['blocks'] for timeslot in block))
