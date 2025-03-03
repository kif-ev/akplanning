from datetime import datetime, timedelta

from django.test import TestCase
from django.urls import reverse_lazy

from AKModel.models import AK, AKSlot, Event
from AKModel.tests import BasicViewTests
from AKSubmission.forms import AKSubmissionForm


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
