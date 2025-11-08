import json
import traceback
from typing import List

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.storage.base import Message
from django.test import TestCase
from django.urls import reverse, reverse_lazy

from AKModel.models import (
    AK,
    AKCategory,
    AKOrgaMessage,
    AKOwner,
    AKRequirement,
    AKSlot,
    AKTrack,
    ConstraintViolation,
    DefaultSlot,
    Event,
    Room,
)


class BasicViewTests:
    """
    Parent class for "standard" tests of views

    Provided with a list of views and arguments (if necessary), this will test that views
    - render correctly without errors
    - are only reachable with the correct rights (neither too freely nor too restricted)

    To do this, the test creates sample users, fixtures are loaded automatically by the django test framework.
    It also provides helper functions, e.g., to check for correct messages to the user or more simply generate
    the URLs to test

    In this class, methods from :class:`TestCase` will be called at multiple places event though TestCase is not a
    parent of this class but has to be included as parent in concrete implementations of this class seperately.
    It however still makes sense to treat this class as some kind of mixin and not implement it as a child of TestCase,
    since the test framework does not understand the concept of abstract test definitions and would handle this class
    as real test case otherwise, distorting the test results.
    """

    # pylint: disable=no-member
    VIEWS = []
    APP_NAME = ""
    VIEWS_STAFF_ONLY = []
    EDIT_TESTCASES = []

    def setUp(self):  # pylint: disable=invalid-name
        """
        Setup testing by creating sample users
        """
        user_model = get_user_model()
        self.staff_user = user_model.objects.create(
            username="Test Staff User",
            email="teststaff@example.com",
            password="staffpw",
            is_staff=True,
            is_active=True,
        )
        self.admin_user = user_model.objects.create(
            username="Test Admin User",
            email="testadmin@example.com",
            password="adminpw",
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )
        self.deactivated_user = user_model.objects.create(
            username="Test Deactivated User",
            email="testdeactivated@example.com",
            password="deactivatedpw",
            is_staff=True,
            is_active=False,
        )

    def _name_and_url(self, view_name):
        """
        Get full view name (with prefix if there is one) and url from raw view definition

        :param view_name: raw definition of a view
        :type view_name: (str, dict)
        :return: full view name with prefix if applicable, url of the view
        :rtype: str, str
        """
        view_name_with_prefix = (
            f"{self.APP_NAME}:{view_name[0]}" if self.APP_NAME != "" else view_name[0]
        )
        url = reverse(view_name_with_prefix, kwargs=view_name[1])
        return view_name_with_prefix, url

    def _assert_message(self, response, expected_message, msg_prefix=""):
        """
        Assert that the correct message is shown and cause test to fail if not

        :param response: response to check
        :param expected_message: message that should be shown
        :param msg_prefix: prefix for the error message when test fails
        """
        messages: List[Message] = list(get_messages(response.wsgi_request))

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
        """
        Test the list of public views (as specified in "VIEWS") for error-free rendering
        """
        for view_name in self.VIEWS:
            view_name_with_prefix, url = self._name_and_url(view_name)
            try:
                response = self.client.get(url)
                self.assertEqual(
                    response.status_code,
                    200,
                    msg=f"{view_name_with_prefix} ({url}) broken",
                )
            except Exception:  # pylint: disable=broad-exception-caught
                self.fail(
                    f"An error occurred during rendering of {view_name_with_prefix} ({url}):"
                    f"\n\n{traceback.format_exc()}"
                )

    def test_access_control_staff_only(self):
        """
        Test whether internal views (as specified in "VIEWS_STAFF_ONLY" are visible to staff users and staff users only
        """
        # Not logged in? Views should not be visible
        self.client.logout()
        for view_name_info in self.VIEWS_STAFF_ONLY:
            expected_response_code = (
                302 if len(view_name_info) == 2 else view_name_info[2]
            )
            view_name_with_prefix, url = self._name_and_url(view_name_info)
            response = self.client.get(url)
            self.assertEqual(
                response.status_code,
                expected_response_code,
                msg=f"{view_name_with_prefix} ({url}) accessible by non-staff",
            )

        # Logged in? Views should be visible
        self.client.force_login(self.staff_user)
        for view_name_info in self.VIEWS_STAFF_ONLY:
            view_name_with_prefix, url = self._name_and_url(view_name_info)
            try:
                response = self.client.get(url)
                self.assertEqual(
                    response.status_code,
                    200,
                    msg=f"{view_name_with_prefix} ({url}) should be accessible for staff (but isn't)",
                )
            except Exception:  # pylint: disable=broad-exception-caught
                self.fail(
                    f"An error occurred during rendering of {view_name_with_prefix} ({url}):"
                    f"\n\n{traceback.format_exc()}"
                )

        # Disabled user? Views should not be visible
        self.client.force_login(self.deactivated_user)
        for view_name_info in self.VIEWS_STAFF_ONLY:
            expected_response_code = (
                302 if len(view_name_info) == 2 else view_name_info[2]
            )
            view_name_with_prefix, url = self._name_and_url(view_name_info)
            response = self.client.get(url)
            self.assertEqual(
                response.status_code,
                expected_response_code,
                msg=f"{view_name_with_prefix} ({url}) still accessible for deactivated user",
            )

    def _to_sendable_value(self, val):
        """
        Create representation sendable via POST from form data

        Needed to automatically check create, update and delete views

        :param val: value to prepare
        :type val: any
        :return: prepared value (normally either raw value or primary key of complex object)
        """
        if isinstance(val, list):
            return [e.pk for e in val]
        if type(val) == "RelatedManager":  # pylint: disable=unidiomatic-typecheck
            return [e.pk for e in val.all()]
        return val

    def test_submit_edit_form(self):
        """
        Test edit forms (as specified in "EDIT_TESTCASES") in the most simple way (sending them again unchanged)
        """
        for testcase in self.EDIT_TESTCASES:
            self._test_submit_edit_form(testcase)

    def _test_submit_edit_form(self, testcase):
        """
        Test a single edit form by rendering and sending it again unchanged

        This will test for correct rendering, dispatching/redirecting, messages and access control handling

        :param testcase: details of the form to test
        """
        name, url = self._name_and_url((testcase["view"], testcase["kwargs"]))
        form_name = testcase.get("form_name", "form")
        expected_code = testcase.get("expected_code", 302)
        if "target_view" in testcase.keys():
            kwargs = testcase.get("target_kwargs", testcase["kwargs"])
            _, target_url = self._name_and_url((testcase["target_view"], kwargs))
        else:
            target_url = url
        expected_message = testcase.get("expected_message", "")
        admin_user = testcase.get("admin", False)

        if admin_user:
            self.client.force_login(self.admin_user)
        else:
            self.client.logout()

        response = self.client.get(url)
        self.assertEqual(
            response.status_code,
            200,
            msg=f"{name}: Could not load edit form via GET ({url})",
        )

        form = response.context[form_name]
        data = {k: self._to_sendable_value(v) for k, v in form.initial.items()}

        response = self.client.post(url, data=data)
        if expected_code == 200:
            self.assertEqual(
                response.status_code, 200, msg=f"{name}: Did not return 200 ({url}"
            )
        elif expected_code == 302:
            self.assertRedirects(
                response,
                target_url,
                msg_prefix=f"{name}: Did not redirect ({url} -> {target_url}",
            )
        if expected_message != "":
            self._assert_message(response, expected_message, msg_prefix=f"{name}")


class ModelViewTests(BasicViewTests, TestCase):
    """
    Basic view test cases for views from AKModel plus some custom tests
    """

    fixtures = ["model.json"]

    ADMIN_MODELS = [
        (Event, "event"),
        (AKOwner, "akowner"),
        (AKCategory, "akcategory"),
        (AKTrack, "aktrack"),
        (AKRequirement, "akrequirement"),
        (AK, "ak"),
        (Room, "room"),
        (AKSlot, "akslot"),
        (AKOrgaMessage, "akorgamessage"),
        (ConstraintViolation, "constraintviolation"),
        (DefaultSlot, "defaultslot"),
    ]

    VIEWS_STAFF_ONLY = [
        ("admin:index", {}),
        ("admin:event_status", {"event_slug": "kif42"}),
        ("admin:event_requirement_overview", {"event_slug": "kif42"}),
        ("admin:ak_csv_export", {"event_slug": "kif42"}),
        ("admin:ak_wiki_export", {"slug": "kif42"}),
        ("admin:ak_delete_orga_messages", {"event_slug": "kif42"}),
        ("admin:ak_slide_export", {"event_slug": "kif42"}),
        ("admin:default-slots-editor", {"event_slug": "kif42"}),
        ("admin:room-import", {"event_slug": "kif42"}),
        ("admin:new_event_wizard_start", {}),
    ]

    EDIT_TESTCASES = [
        {
            "view": "admin:default-slots-editor",
            "kwargs": {"event_slug": "kif42"},
            "admin": True,
        },
    ]

    def test_admin(self):
        """
        Test basic admin functionality (displaying and interacting with model instances)
        """
        self.client.force_login(self.admin_user)
        for model in self.ADMIN_MODELS:
            # Special treatment for a subset of views (where we exchanged default functionality, e.g., create views)
            if model[1] == "event":
                _, url = self._name_and_url(("admin:new_event_wizard_start", {}))
            elif model[1] == "room":
                _, url = self._name_and_url(("admin:room-new", {}))
            # Otherwise, just call the creation form view
            else:
                _, url = self._name_and_url((f"admin:AKModel_{model[1]}_add", {}))
            response = self.client.get(url)
            self.assertEqual(
                response.status_code,
                200,
                msg=f"Add form for model {model[1]} ({url}) broken",
            )

        for model in self.ADMIN_MODELS:
            # Test the update view using the first existing instance of each model
            m = model[0].objects.first()
            if m is not None:
                _, url = self._name_and_url(
                    (f"admin:AKModel_{model[1]}_change", {"object_id": m.pk})
                )
                response = self.client.get(url)
                self.assertEqual(
                    response.status_code,
                    200,
                    msg=f"Edit form for model {model[1]} ({url}) broken",
                )

    def test_wiki_export(self):
        """
        Test wiki export
        This will test whether the view renders at all and whether the export list contains the correct AKs
        """
        self.client.force_login(self.admin_user)

        export_url = reverse_lazy("admin:ak_wiki_export", kwargs={"slug": "kif42"})
        response = self.client.get(export_url)
        self.assertEqual(response.status_code, 200, "Export not working at all")

        export_count = 0
        for _, aks in response.context["categories_with_aks"]:
            for ak in aks:
                self.assertEqual(
                    ak.include_in_export,
                    True,
                    f"AK with export flag set to False (pk={ak.pk}) included in export",
                )
                self.assertNotEqual(
                    ak.pk,
                    1,
                    "AK known to be excluded from export (PK 1) included in export",
                )
                export_count += 1

        self.assertEqual(
            export_count,
            AK.objects.filter(event_id=2, include_in_export=True).count(),
            "Wiki export contained the wrong number of AKs",
        )

    def test_list_api_views(self):
        """
        Test list API views, checking whether they load correctly
        and include the correct items and fields
        """
        api_views = [
            ("model:AK-list", AK, '__all__'),
            ("model:AKOwner-list", AKOwner, '__all__'),
            ("model:AKCategory-list", AKCategory, '__all__'),
            ("model:AKTrack-list", AKTrack, '__all__'),
            ("model:Room-list", Room, '__all__'),
            ("model:AKSlot-list", AKSlot, '__all__'),
        ]
        event = Event.objects.get(slug="kif42")

        self.client.force_login(self.staff_user)
        for view_name_with_prefix, model, expected_fields in api_views:
            url = reverse(view_name_with_prefix, kwargs={"event_slug": "kif42"})
            if expected_fields == '__all__':
                expected_fields = [f.name for f in model._meta.get_fields() if not f.auto_created]
            try:
                response = self.client.get(url)
                self.assertEqual(
                    response.status_code,
                    200,
                    msg=f"API view {view_name_with_prefix} ({url}) is not loading correctly",
                )
            except Exception:  # pylint: disable=broad-exception-caught
                self.fail(
                    f"An error occurred loading api view {view_name_with_prefix} ({url}):"
                    f"\n\n{traceback.format_exc()}"
                )
            parsed_response = json.loads(response.content.decode("utf-8"))
            included_items = set(item["id"] for item in parsed_response)
            expected_items = set(obj.pk for obj in model.objects.filter(event=event))
            self.assertEqual(
                included_items,
                expected_items,
                msg=f"API view {view_name_with_prefix} ({url}) is not including the correct items. "
                    f"Missing: {expected_items - included_items}, Extra: {included_items - expected_items}",
            )
            missing_fields = [field for field in expected_fields if field not in parsed_response[0].keys()]
            self.assertEqual(
                missing_fields,
                [],
                msg=f"API view {view_name_with_prefix} ({url}) is missing fields in the output: {missing_fields}",
            )


    def test_api_root_view(self):
        """
        Ensure API endpoint is reachable (without login)
        """
        self.client.logout()
        url = reverse("model:api-root", kwargs={"event_slug": "kif42"})
        response = self.client.get(url)
        self.assertEqual(
            response.status_code,
            200,
            msg="API root view not reachable",
        )


    def test_api_root_view_invalid_event_slug(self):
        """
        Ensure API is not delivered for invalid event slugs
        """
        url = reverse("model:api-root", kwargs={"event_slug": "invalidslug"})
        response = self.client.get(url)
        self.assertEqual(
            response.status_code,
            404,
            msg="API root view did not return 404 for invalid event slug",
        )
