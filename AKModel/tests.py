from django.contrib.auth.models import User
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

    def testViewsFor200(self):
        for view_name in self.VIEWS:
            view_name_with_prefix, url = self._name_and_url(view_name)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, msg=f"{view_name_with_prefix} ({url}) broken")

    def testAccessControlStaffOnly(self):
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

    def testAdmin(self):
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
