from datetime import datetime, timedelta

from django.test import TestCase
from django.urls import reverse_lazy

from AKModel.models import AK, AKSlot, Event
from AKModel.tests.test_views import BasicViewTests
from AKSubmission.forms import AKDurationForm, AKSubmissionForm


class ModelViewTests(BasicViewTests, TestCase):
    """
    Testcases for AKSubmission app.

    This extends :class:`BasicViewTests` for standard view and edit testcases
    that are specified in this class as VIEWS and EDIT_TESTCASES.

    Additionally several additional testcases, in particular to test the API
    and the dispatching for owner selection and editing are specified.
    """
    fixtures = ['model.json']

    VIEWS = [
        ('submission_overview', {'event_slug': 'kif42'}),
        ('ak_detail', {'event_slug': 'kif42', 'pk': 1}),
        ('ak_history', {'event_slug': 'kif42', 'pk': 1}),
        ('ak_edit', {'event_slug': 'kif42', 'pk': 1}),
        ('akslot_add', {'event_slug': 'kif42', 'pk': 1}),
        ('akmessage_add', {'event_slug': 'kif42', 'pk': 1}),
        ('akslot_edit', {'event_slug': 'kif42', 'pk': 5}),
        ('akslot_delete', {'event_slug': 'kif42', 'pk': 5}),
        ('ak_list', {'event_slug': 'kif42'}),
        ('ak_list_by_category', {'event_slug': 'kif42', 'category_pk': 4}),
        ('ak_list_by_track', {'event_slug': 'kif42', 'track_pk': 1}),
        ('akowner_create', {'event_slug': 'kif42'}),
        ('akowner_edit', {'event_slug': 'kif42', 'slug': 'a'}),
        ('submit_ak', {'event_slug': 'kif42', 'owner_slug': 'a'}),
        ('submit_ak_wish', {'event_slug': 'kif42'}),
        ('error_not_configured', {'event_slug': 'kif42'}),
    ]

    APP_NAME = 'submit'

    EDIT_TESTCASES = [
        {'view': 'ak_edit', 'target_view': 'ak_detail', 'kwargs': {'event_slug': 'kif42', 'pk': 1},
         'expected_message': "AK successfully updated"},
        {'view': 'akslot_edit', 'target_view': 'ak_detail', 'kwargs': {'event_slug': 'kif42', 'pk': 5},
         'target_kwargs': {'event_slug': 'kif42', 'pk': 1}, 'expected_message': "AK Slot successfully updated"},
        {'view': 'akowner_edit', 'target_view': 'submission_overview', 'kwargs': {'event_slug': 'kif42', 'slug': 'a'},
         'target_kwargs': {'event_slug': 'kif42'}, 'expected_message': "Person Info successfully updated"},
    ]

    def test_akslot_edit_delete_prevention(self):
        """
        Slots planned already may not be modified or deleted in front end
        """
        self.client.logout()

        _, url = self._name_and_url(('akslot_edit', {'event_slug': 'kif42', 'pk': 1}))
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302,
                         msg=f"AK Slot editing ({url}) possible even though slot was already scheduled")
        self._assert_message(response, "You cannot edit a slot that has already been scheduled")

        _, url = self._name_and_url(('akslot_delete', {'event_slug': 'kif42', 'pk': 1}))
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302,
                         msg=f"AK Slot deletion ({url}) possible even though slot was already scheduled")
        self._assert_message(response, "You cannot delete a slot that has already been scheduled")

    def test_slot_creation_deletion(self):
        """
        Test creation and deletion of slots in frontend
        """
        ak_args = {'event_slug': 'kif42', 'pk': 1}
        redirect_url = reverse_lazy(f"{self.APP_NAME}:ak_detail", kwargs=ak_args)

        # Create a valid slot -> Redirect to AK detail page, message to user
        count_slots = AK.objects.get(pk=1).akslot_set.count()
        create_url = reverse_lazy(f"{self.APP_NAME}:akslot_add", kwargs=ak_args)
        response = self.client.post(create_url, {'ak': 1, 'event': 2, 'duration': 1.5})
        self.assertRedirects(response, redirect_url, status_code=302, target_status_code=200,
                             msg_prefix="Did not correctly trigger redirect")
        self.assertEqual(AK.objects.get(pk=1).akslot_set.count(), count_slots + 1,
                         msg="New slot was not correctly saved")

        # Get primary key of newly created Slot
        slot_pk = AK.objects.get(pk=1).akslot_set.order_by('pk').last().pk

        # Edit the recently created slot: Make sure view is accessible, post change
        # -> redirect to detail page, duration updated
        edit_url = reverse_lazy(f"{self.APP_NAME}:akslot_edit", kwargs={'event_slug': 'kif42', 'pk': slot_pk})
        response = self.client.get(edit_url)
        self.assertEqual(response.status_code, 200, msg=f"Cant open edit view for newly created slot ({edit_url})")
        response = self.client.post(edit_url, {'ak': 1, 'event': 2, 'duration': 2})
        self.assertRedirects(response, redirect_url, status_code=302, target_status_code=200,
                             msg_prefix="Did not correctly trigger redirect")
        self.assertEqual(AKSlot.objects.get(pk=slot_pk).duration, 2,
                         msg="Slot was not correctly changed")

        # Delete recently created slot: Make sure view is accessible, post deletion
        # -> redirect to detail page, slot deleted, message to user
        deletion_url = reverse_lazy(f"{self.APP_NAME}:akslot_delete", kwargs={'event_slug': 'kif42', 'pk': slot_pk})
        response = self.client.get(deletion_url)
        self.assertEqual(response.status_code, 200,
                         msg="Cant open deletion view for newly created slot ({deletion_url})")
        response = self.client.post(deletion_url, {})
        self.assertRedirects(response, redirect_url, status_code=302, target_status_code=200,
                             msg_prefix="Did not correctly trigger redirect")
        self.assertFalse(AKSlot.objects.filter(pk=slot_pk).exists(), msg="Slot was not correctly deleted")
        self.assertEqual(AK.objects.get(pk=1).akslot_set.count(), count_slots, msg="AK still has to many slots")

    def test_ak_owner_editing(self):
        """
        Test dispatch of user editing requests
        """
        edit_url = reverse_lazy(f"{self.APP_NAME}:akowner_edit_dispatch", kwargs={'event_slug': 'kif42'})

        base_url = reverse_lazy(f"{self.APP_NAME}:submission_overview", kwargs={'event_slug': 'kif42'})

        # Empty form/no user selected -> start page
        response = self.client.post(edit_url, {'owner_id': -1})
        self.assertRedirects(response, base_url, status_code=302, target_status_code=200,
                             msg_prefix="Did not redirect to start page even though no user was selected")
        self._assert_message(response, "No user selected")

        # Correct selection -> user edit page for that user
        edit_redirect_url = reverse_lazy(f"{self.APP_NAME}:akowner_edit", kwargs={'event_slug': 'kif42', 'slug': 'a'})
        response = self.client.post(edit_url, {'owner_id': 1})
        self.assertRedirects(response, edit_redirect_url, status_code=302, target_status_code=200,
                             msg_prefix=f"Dispatch redirect failed (should go to {edit_redirect_url})")

    def test_ak_owner_selection(self):
        """
        Test dispatch of owner selection requests
        """
        select_url = reverse_lazy(f"{self.APP_NAME}:akowner_select", kwargs={'event_slug': 'kif42'})
        create_url = reverse_lazy(f"{self.APP_NAME}:akowner_create", kwargs={'event_slug': 'kif42'})

        # Empty user selection -> create a new user view
        response = self.client.post(select_url, {'owner_id': -1})
        self.assertRedirects(response, create_url, status_code=302, target_status_code=200,
                             msg_prefix="Did not redirect to user create view even though no user was specified")

        # Valid user selected -> redirect to view that allows to add a new AK with this user as owner
        add_redirect_url = reverse_lazy(f"{self.APP_NAME}:submit_ak", kwargs={'event_slug': 'kif42', 'owner_slug': 'a'})
        response = self.client.post(select_url, {'owner_id': 1})
        self.assertRedirects(response, add_redirect_url, status_code=302, target_status_code=200,
                             msg_prefix=f"Dispatch redirect to ak submission page failed "
                                        f"(should go to {add_redirect_url})")

    def test_orga_message_submission(self):
        """
        Test submission and storing of direct confident messages to organizers
        """
        form_url = reverse_lazy(f"{self.APP_NAME}:akmessage_add", kwargs={'event_slug': 'kif42', 'pk': 1})
        detail_url = reverse_lazy(f"{self.APP_NAME}:ak_detail", kwargs={'event_slug': 'kif42', 'pk': 1})

        count_messages = AK.objects.get(pk=1).akorgamessage_set.count()

        # Test that submission view is accessible
        response = self.client.get(form_url)
        self.assertEqual(response.status_code, 200, msg="Could not load message form view")

        # Test submission itself and the following redirect -> AK detail page
        response = self.client.post(form_url, {'ak': 1, 'event': 2, 'text': 'Test message text'})
        self.assertRedirects(response, detail_url, status_code=302, target_status_code=200,
                             msg_prefix=f"Did not trigger redirect to ak detail page ({detail_url})")

        # Make sure message was correctly saved in database and user is notified about that
        self._assert_message(response, "Message to organizers successfully saved")
        self.assertEqual(AK.objects.get(pk=1).akorgamessage_set.count(), count_messages + 1,
                         msg="Message was not correctly saved")

    def test_interest_api(self):
        """
        Test interest indicating API (access, functionality)
        """
        interest_api_url = "/kif42/api/ak/1/indicate-interest/"

        ak = AK.objects.get(pk=1)
        event = Event.objects.get(slug='kif42')
        ak_interest_counter = ak.interest_counter

        # Check Access method (only POST)
        response = self.client.get(interest_api_url)
        self.assertEqual(response.status_code, 405, "Should not be accessible via GET")

        event.interest_start = datetime.now().astimezone(event.timezone) + timedelta(minutes=-10)
        event.interest_end = datetime.now().astimezone(event.timezone) + timedelta(minutes=+10)
        event.save()

        # Test correct indication -> HTTP 200, counter increased
        response = self.client.post(interest_api_url)
        self.assertEqual(response.status_code, 200, f"API end point not working ({interest_api_url})")
        self.assertEqual(AK.objects.get(pk=1).interest_counter, ak_interest_counter + 1, "Counter was not increased")

        event.interest_end = datetime.now().astimezone(event.timezone) + timedelta(minutes=-2)
        event.save()

        # Test indication outside of indication window -> HTTP 403, counter not increased
        response = self.client.post(interest_api_url)
        self.assertEqual(response.status_code, 403,
                         "API end point still reachable even though interest indication window ended "
                         "({interest_api_url})")
        self.assertEqual(AK.objects.get(pk=1).interest_counter, ak_interest_counter + 1,
                         "Counter was increased even though interest indication window ended")

        # Test call for non-existing AK -> HTTP 403
        invalid_interest_api_url = "/kif42/api/ak/-1/indicate-interest/"
        response = self.client.post(invalid_interest_api_url)
        self.assertEqual(response.status_code, 404, f"Invalid URL reachable ({interest_api_url})")

    def test_adding_of_unknown_user(self):
        """
        Test adding of a previously not existing owner to an AK
        """
        # Pre-Check: AK detail page existing?
        detail_url = reverse_lazy(f"{self.APP_NAME}:ak_detail", kwargs={'event_slug': 'kif42', 'pk': 1})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200, msg="Could not load ak detail view")

        # Make sure AK detail page contains a link to add a new owner
        edit_url = reverse_lazy(f"{self.APP_NAME}:ak_edit", kwargs={'event_slug': 'kif42', 'pk': 1})
        response = self.client.get(edit_url)
        self.assertEqual(response.status_code, 200, msg="Could not load ak detail view")
        self.assertContains(response, "Add person not in the list yet",
                            msg_prefix="Link to add unknown user not contained")

        # Check adding of a new owner by posting an according request
        # -> Redirect to AK detail page, message to user, owners list updated
        self.assertEqual(AK.objects.get(pk=1).owners.count(), 1)
        add_new_user_to_ak_url = reverse_lazy(f"{self.APP_NAME}:akowner_create", kwargs={'event_slug': 'kif42'}) \
                                 + "?add_to_existing_ak=1"
        response = self.client.post(add_new_user_to_ak_url,
                                    {'name': 'New test owner', 'event': Event.get_by_slug('kif42').pk})
        self.assertRedirects(response, detail_url,
                             msg_prefix=f"No correct redirect: {add_new_user_to_ak_url} (POST) -> {detail_url}")
        self._assert_message(response, "Added 'New test owner' as new owner of 'Test AK Inhalt'")
        self.assertEqual(AK.objects.get(pk=1).owners.count(), 2)

    def test_visibility_requirements_in_submission_form(self):
        """
        Test visibility of requirements field in submission form
        """
        event = Event.get_by_slug('kif42')
        form = AKSubmissionForm(data={'name': 'Test AK', 'event': event}, instance=None, initial={"event": event})
        self.assertIn('requirements', form.fields,
                      msg="Requirements field not present in form even though event has requirements")

        event2 = Event.objects.create(name='Event without requirements',
                                      slug='no_req',
                                      start=datetime.now().astimezone(event.timezone),
                                      end=datetime.now().astimezone(event.timezone),
                                      active=True)
        form2 = AKSubmissionForm(data={'name': 'Test AK', 'event': event2}, instance=None, initial={"event": event2})
        self.assertNotIn('requirements', form2.fields,
                         msg="Requirements field should not be present for events without requirements")

    def test_visibility_types_in_submission_form(self):
        """
        Test visibility of types field in submission form
        """
        event = Event.get_by_slug('kif42')
        form = AKSubmissionForm(data={'name': 'Test AK', 'event': event}, instance=None, initial={"event": event})
        self.assertIn('types', form.fields,
                      msg="Requirements field not present in form even though event has requirements")

        event2 = Event.objects.create(name='Event without types',
                                      slug='no_types',
                                      start=datetime.now().astimezone(event.timezone),
                                      end=datetime.now().astimezone(event.timezone),
                                      active=True)
        form2 = AKSubmissionForm(data={'name': 'Test AK', 'event': event2}, instance=None, initial={"event": event2})
        self.assertNotIn('types', form2.fields,
                         msg="Requirements field should not be present for events without types")

    def test_duration_validation_in_submission_form(self):
        """
        Test that the durations field only accepts lines that can be converted into meaningful durations
        and that durations longer than the event are clamped to the length of the event
        """
        def durations_form(durations, event):
            form = AKSubmissionForm(data={'name': 'Test AK', 'event': event.pk, 'durations': durations,
                                          'availabilities': '{"availabilities": []}'},
                                    instance=None, initial={"event": event})
            form.is_valid()
            return form

        event = Event.get_by_slug('kif42')

        for valid, expected in [("2", [2]), ("1.5", [1.5]), ("1,5", [1.5]), ("1:30", [1.5]),
                                ("2\n1.5\n0:45", [2, 1.5, 0.75]), ("2\r\n\r\n 1,5 \n", [2, 1.5])]:
            form = durations_form(valid, event)
            self.assertIsNone(form.errors.get('durations'), msg=f"Valid durations '{valid}' were rejected")
            self.assertEqual(form.cleaned_data['durations'], expected,
                             msg=f"Durations '{valid}' were not correctly converted")

        for invalid in ["abc", "two", "1:ab", "1:2:3", "1,2,3", "nan", "inf", "-inf", "0", "-1", "2\nabc\n1.5",
                        "1 2", "1,5 h", "1 - 2 Stunden", "Unbekannt", "-1e30", "0.001"]:
            self.assertIsNotNone(durations_form(invalid, event).errors.get('durations'),
                                 msg=f"Invalid durations '{invalid}' were accepted")

        # All invalid lines should be reported at once, each as a whole line
        self.assertEqual(durations_form("abc\n2\n1,5 h\nweiß ich noch nicht", event).errors['durations'],
                         ['"abc" is not a valid duration', '"1,5 h" is not a valid duration',
                          '"weiß ich noch nicht" is not a valid duration'])

        # Durations longer than the event (kif42 lasts four days, i.e., 96 hours) are clamped to the event length
        for too_long in ["97", "100", "1000", "200:00", "96,5", "1e30"]:
            form = durations_form(too_long, event)
            self.assertIsNone(form.errors.get('durations'), msg=f"Too long duration '{too_long}' was rejected")
            self.assertEqual(form.cleaned_data['durations'], [96],
                             msg=f"Too long duration '{too_long}' was not clamped to the event length")
            self.assertEqual(form.clamped_durations, [too_long],
                             msg=f"Clamping of too long duration '{too_long}' was not recorded")

        # Durations within the event length are not recorded as clamped
        self.assertEqual(durations_form("2\n96", event).clamped_durations, [])

        # Clamping only affects the lines that contain durations that are too long, also for short events
        short_event = Event.objects.create(name='Short event',
                                           slug='short',
                                           start=event.start,
                                           end=event.start + timedelta(hours=3, minutes=30),
                                           active=True)
        form = durations_form("1:30\n5\n3.5", short_event)
        self.assertIsNone(form.errors.get('durations'))
        self.assertEqual(form.cleaned_data['durations'], [1.5, 3.5, 3.5],
                         msg="Durations were not correctly clamped to the length of a short event")
        self.assertEqual(form.clamped_durations, ["5"])

        # Without a valid event, the form is invalid (durations cannot be checked against the event length)
        form = AKDurationForm(data={'ak': 1, 'event': -1, 'duration': "1e30"})
        self.assertFalse(form.is_valid())
        self.assertIn('event', form.errors)

    def test_submission_with_too_long_durations(self):
        """
        Test that slots with durations longer than the event are shortened to the event length when submitting an AK
        and that the user is warned about this
        """
        submit_url = reverse_lazy(f"{self.APP_NAME}:submit_ak", kwargs={'event_slug': 'kif42', 'owner_slug': 'a'})
        data = {'name': 'AK with long slots', 'owners': [1], 'category': 4, 'event': 2, 'types': [1],
                'description': 'Test description', 'goal': 'Test goal',
                'availabilities': '{"availabilities": []}'}

        # Durations within the event length -> slots saved as given, no warning
        response = self.client.post(submit_url, data | {'durations': "2\n1:30"})
        ak = AK.objects.get(name='AK with long slots')
        self.assertRedirects(response, ak.detail_url, msg_prefix="AK submission failed")
        self.assertEqual(sorted(s.duration for s in ak.akslot_set.all()), [1.5, 2])
        self._assert_message(response, "AK successfully created")

        # Too long durations -> slots clamped to event length (kif42 lasts 96 hours), user is warned
        response = self.client.post(submit_url, data | {'name': 'AK with too long slots', 'durations': "2\n100\n200:00"})
        ak = AK.objects.get(name='AK with too long slots')
        self.assertRedirects(response, ak.detail_url, msg_prefix="AK submission with too long durations failed")
        self.assertEqual(sorted(s.duration for s in ak.akslot_set.all()), [2, 96, 96],
                         msg="Too long durations were not clamped to the event length when saving slots")
        self._assert_message(response, "The following durations were longer than the event and were shortened to "
                                       "the length of the event (96 hours): 100, 200:00")

    def test_slot_duration_handling(self):
        """
        Test that adding and editing slots handles durations like the submission form
        (same input formats, invalid values rejected, too long durations clamped to the event length with a warning)
        """
        ak_args = {'event_slug': 'kif42', 'pk': 1}
        detail_url = reverse_lazy(f"{self.APP_NAME}:ak_detail", kwargs=ak_args)
        create_url = reverse_lazy(f"{self.APP_NAME}:akslot_add", kwargs=ak_args)
        clamp_message = ("The following durations were longer than the event and were shortened to the length of "
                         "the event (96 hours): {}")

        # Alternative input formats are accepted
        for raw, expected in [("1:30", 1.5), ("1,5", 1.5), ("2", 2)]:
            response = self.client.post(create_url, {'ak': 1, 'event': 2, 'duration': raw})
            self.assertRedirects(response, detail_url, msg_prefix=f"Adding slot with duration '{raw}' failed")
            self._assert_message(response, "AK Slot successfully added")
            self.assertEqual(AKSlot.objects.filter(ak=1).order_by('pk').last().duration, expected)

        # Invalid durations are rejected and no slot is created
        count_slots = AKSlot.objects.filter(ak=1).count()
        for invalid in ["abc", "1:ab", "nan", "inf", "0", "-1"]:
            response = self.client.post(create_url, {'ak': 1, 'event': 2, 'duration': invalid})
            self.assertEqual(response.status_code, 200, msg=f"Invalid duration '{invalid}' was accepted")
            self.assertIn('duration', response.context['form'].errors)
        self.assertEqual(AKSlot.objects.filter(ak=1).count(), count_slots, msg="Slot with invalid duration created")

        # Too long durations are clamped to the event length and the user is warned
        response = self.client.post(create_url, {'ak': 1, 'event': 2, 'duration': "200"})
        self.assertRedirects(response, detail_url, msg_prefix="Adding slot with too long duration failed")
        self._assert_message(response, clamp_message.format("200"))
        slot = AKSlot.objects.filter(ak=1).order_by('pk').last()
        self.assertEqual(slot.duration, 96)

        # The same applies when editing a slot
        edit_url = reverse_lazy(f"{self.APP_NAME}:akslot_edit", kwargs={'event_slug': 'kif42', 'pk': slot.pk})
        response = self.client.post(edit_url, {'ak': 1, 'event': 2, 'duration': "0:45"})
        self.assertRedirects(response, detail_url, msg_prefix="Editing slot failed")
        self._assert_message(response, "AK Slot successfully updated")
        self.assertEqual(AKSlot.objects.get(pk=slot.pk).duration, 0.75)

        response = self.client.post(edit_url, {'ak': 1, 'event': 2, 'duration': "abc"})
        self.assertEqual(response.status_code, 200, msg="Invalid duration was accepted when editing a slot")
        self.assertEqual(AKSlot.objects.get(pk=slot.pk).duration, 0.75)

        response = self.client.post(edit_url, {'ak': 1, 'event': 2, 'duration': "100:00"})
        self.assertRedirects(response, detail_url, msg_prefix="Editing slot with too long duration failed")
        self._assert_message(response, clamp_message.format("100:00"))
        self.assertEqual(AKSlot.objects.get(pk=slot.pk).duration, 96)

    def test_wish_to_ak_default_slot_clamped(self):
        """
        Test that the default slot created when a wish becomes an AK is not longer than the event
        """
        # Shorten event such that the default slot length (2 hours) exceeds the event length
        event = Event.get_by_slug('kif42')
        event.end = event.start + timedelta(hours=1, minutes=30)
        event.save()

        wish = AK.objects.get(pk=3)
        wish.akslot_set.all().delete()
        edit_url = reverse_lazy(f"{self.APP_NAME}:ak_edit", kwargs={'event_slug': 'kif42', 'pk': wish.pk})
        response = self.client.post(edit_url, {
            'name': wish.name, 'short_name': wish.short_name, 'description': wish.description, 'goal': wish.goal,
            'category': wish.category.pk, 'owners': [2], 'event': event.pk, 'types': [1],
            'availabilities': '{"availabilities": []}',
        })
        self.assertRedirects(response, wish.detail_url, msg_prefix="Turning wish into AK failed")
        self.assertEqual([s.duration for s in AK.objects.get(pk=3).akslot_set.all()], [1.5],
                         msg="Default slot was not clamped to the event length")
