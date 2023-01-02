import traceback
from typing import List

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.contrib.messages.storage.base import Message
from django.test import TestCase
from django.urls import reverse_lazy

from AKModel.models import Event, AKOwner, AKCategory, AKTrack, AKRequirement, AK, Room, AKSlot, AKOrgaMessage, \
    ConstraintViolation, DefaultSlot


class BasicViewTests:
    VIEWS = []
    APP_NAME = ''
    VIEWS_STAFF_ONLY = []

    def setUp(self):
        self.staff_user = User.objects.create(
            username='Test Staff User', email='teststaff@example.com', password='staffpw',
            is_staff=True, is_active=True
        )
        self.admin_user = User.objects.create(
            username='Test Admin User', email='testadmin@example.com', password='adminpw',
            is_staff=True, is_superuser=True, is_active=True
        )
        self.deactivated_user = User.objects.create(
            username='Test Deactivated User', email='testdeactivated@example.com', password='deactivatedpw',
            is_staff=True, is_active=False
        )

    def _name_and_url(self, view_name):
        """
        Get full view name (with prefix if there is one) and url from raw view definition

        :param view_name: raw definition of a view
        :type view_name: (str, dict)
        :return: full view name with prefix if applicable, url of the view
        :rtype: str, str
        """
        view_name_with_prefix = f"{self.APP_NAME}:{view_name[0]}" if self.APP_NAME != "" else view_name[0]
        url = reverse_lazy(view_name_with_prefix, kwargs=view_name[1])
        return view_name_with_prefix, url

    def _assert_message(self, response, expected_message, msg_prefix=""):
        messages:List[Message] = list(get_messages(response.wsgi_request))

        msg_count = "No message shown to user"
        msg_content = "Wrong message, expected '{expected_message}'"
        if msg_prefix != "":
            msg_count = f"{msg_prefix}: {msg_count}"
            msg_content = f"{msg_prefix}: {msg_content}"

        # Check that the last message correctly reports the issue
        # (there might be more messages from previous calls that were not already rendered)
        self.assertGreater(len(messages), 0, msg=msg_count)
        self.assertEqual(messages[-1].message, expected_message, msg=msg_content)

    def test_views_for_200(self):
        for view_name in self.VIEWS:
            view_name_with_prefix, url = self._name_and_url(view_name)
            try:
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, msg=f"{view_name_with_prefix} ({url}) broken")
            except Exception as e:
                self.fail(f"An error occurred during rendering of {view_name_with_prefix} ({url}):\n\n{traceback.format_exc()}")

    def test_access_control_staff_only(self):
        self.client.logout()
        for view_name in self.VIEWS_STAFF_ONLY:
            view_name_with_prefix, url = self._name_and_url(view_name)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, msg=f"{view_name_with_prefix} ({url}) accessible by non-staff")

        self.client.force_login(self.staff_user)
        for view_name in self.VIEWS_STAFF_ONLY:
            view_name_with_prefix, url = self._name_and_url(view_name)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200,
                             msg=f"{view_name_with_prefix} ({url}) should be accessible for staff (but isn't)")

        self.client.force_login(self.deactivated_user)
        for view_name in self.VIEWS_STAFF_ONLY:
            view_name_with_prefix, url = self._name_and_url(view_name)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302,
                             msg=f"{view_name_with_prefix} ({url}) still accessible for deactivated user")


class ModelViewTests(BasicViewTests, TestCase):
    fixtures = ['model.json']

    ADMIN_MODELS = [
        (Event, 'event'), (AKOwner, 'akowner'), (AKCategory, 'akcategory'), (AKTrack, 'aktrack'),
        (AKRequirement, 'akrequirement'), (AK, 'ak'), (Room, 'room'), (AKSlot, 'akslot'),
        (AKOrgaMessage, 'akorgamessage'), (ConstraintViolation, 'constraintviolation'),
        (DefaultSlot, 'defaultslot')
    ]

    VIEWS_STAFF_ONLY = [
        ('admin:index', {}),
        ('admin:event_status', {'slug': 'kif42'}),
        ('admin:event_requirement_overview', {'event_slug': 'kif42'}),
        ('admin:ak_csv_export', {'event_slug': 'kif42'}),
        ('admin:ak_wiki_export', {'slug': 'kif42'}),
        ('admin:ak_delete_orga_messages', {'event_slug': 'kif42'}),
        ('admin:ak_slide_export', {'event_slug': 'kif42'}),
        ('admin:default-slots-editor', {'event_slug': 'kif42'}),
        ('admin:room-import', {'event_slug': 'kif42'}),
        ('admin:new_event_wizard_start', {}),
    ]

    def test_admin(self):
        self.client.force_login(self.admin_user)
        for model in self.ADMIN_MODELS:
            if model[1] == "event":
                continue
            view_name_with_prefix, url = self._name_and_url((f'admin:AKModel_{model[1]}_add', {}))
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, msg=f"Add form for model {model[1]} ({url}) broken")

        for model in self.ADMIN_MODELS:
            m = model[0].objects.first()
            if m is not None:
                view_name_with_prefix, url = self._name_and_url((f'admin:AKModel_{model[1]}_change', {'object_id': m.pk}))
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, msg=f"Edit form for model {model[1]} ({url}) broken")

    def test_wiki_export(self):
        self.client.force_login(self.admin_user)

        export_url = reverse_lazy(f"admin:ak_wiki_export", kwargs={'slug': 'kif42'})
        response = self.client.get(export_url)
        self.assertEqual(response.status_code, 200, "Export not working at all")

        export_count = 0
        for category, aks in response.context["categories_with_aks"]:
            for ak in aks:
                self.assertEqual(ak.include_in_export, True, f"AK with export flag set to False (pk={ak.pk}) included in export")
                self.assertNotEqual(ak.pk, 1, "AK known to be excluded from export (PK 1) included in export")
                export_count += 1

        self.assertEqual(export_count, AK.objects.filter(event_id=2, include_in_export=True).count(),
                         "Wiki export contained the wrong number of AKs")
