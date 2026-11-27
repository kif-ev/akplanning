import json
import re
import traceback
from datetime import datetime, timedelta
from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.storage.base import Message
from django.core import signing
from django.test import override_settings, TestCase
from django.urls import reverse, reverse_lazy
from typing import Any, List
from urllib.parse import urlencode

from AKModel.availability.models import Availability
from AKModel.models import (
    AK,
    AKCategory,
    AKOrgaMessage,
    AKOwner,
    AKRequirement,
    AKSlot,
    AKTrack,
    AKType,
    ConstraintViolation,
    DefaultSlot,
    Event,
    Room,
)
from AKModel.typing_utils import TestCaseMixinBase


class BasicViewTests(TestCaseMixinBase):
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
    VIEWS: list[tuple[str, dict] | tuple[str, dict, int]] = []
    APP_NAME = ""
    VIEWS_STAFF_ONLY: list[tuple[str, dict] | tuple[str, dict, int]] = []
    EDIT_TESTCASES: list[dict] = []

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

    ADMIN_MODELS: list[tuple[Any, str]] = [
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
        ("admin:room-import-template", {"event_slug": "kif42"}),
        ("admin:new_event_wizard_start", {}),
    ]

    EDIT_TESTCASES = [
        {
            "view": "admin:default-slots-editor",
            "kwargs": {"event_slug": "kif42"},
            "admin": True,
        },
    ]

    def _expected_slide_ak_count(self, event, data):
        """Calculate expected number of AK slides for the given export config."""
        category_ids = [int(pk) for pk in data.get("categories", [])]
        type_ids = [int(pk) for pk in data.get("types", [])]
        categories = AKCategory.objects.filter(id__in=category_ids) if category_ids else None
        types = None
        if type_ids and len(type_ids) < event.aktype_set.count():
            types = AKType.objects.filter(id__in=type_ids)

        categories_with_aks = event.get_categories_with_aks(
                filter_func=lambda ak: data["include_wishes"] if ak.wish else (
                        (not data["presentation_mode"])
                        or (ak.present or (ak.present is None and ak.category.present_by_default))),
                types=types,
                types_all_selected_only=data.get("types_all_selected_only", False),
                sort_func=lambda ak: ak.wish,
                categories=categories,
        )
        return sum(len(ak_list) for _, ak_list in categories_with_aks)

    def _prepare_types_for_export_tests(self, event):
        """Create a deterministic type setup so type-based filtering paths are exercised."""
        existing_types = list(event.aktype_set.all())
        primary_type = existing_types[0] if existing_types else AKType.objects.create(event=event, name="Type A",
                                                                                      slug="type-a")
        secondary_type = AKType.objects.create(event=event, name="Type B", slug="type-b")

        ak1 = AK.objects.get(pk=1)
        ak2 = AK.objects.get(pk=2)
        ak4 = AK.objects.get(pk=4)
        ak1.types.set([primary_type])
        ak2.types.set([secondary_type])
        ak4.types.set([primary_type, secondary_type])

        return primary_type, secondary_type

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

    def test_slide_export_web_view(self):
        """
        Test web slide export
        This ensures the export endpoint publishes a public slide URL and that the public page renders correctly.
        """
        self.client.force_login(self.admin_user)

        event = Event.objects.get(slug="kif42")
        export_url = reverse_lazy("admin:ak_slide_export", kwargs={"event_slug": "kif42"})
        data = {
            "num_next": 3,
            "presentation_mode": "False",
            "include_wishes": "True",
            "export_mode": "web",
            "categories": [str(category.pk) for category in event.akcategory_set.all()],
        }
        if event.aktype_set.exists():
            data["types"] = [str(ak_type.pk) for ak_type in event.aktype_set.all()]

        response = self.client.post(export_url, data=data)
        self.assertEqual(response.status_code, 302, "Web slide export did not redirect to a public URL")
        public_url = str(reverse_lazy("model:ak_slides_public", kwargs={"event_slug": "kif42"}))
        self.assertTrue(
                response["Location"].startswith(public_url),
                msg=f"Unexpected redirect target: {response['Location']}",
        )

        self.client.logout()
        public_response = self.client.get(response["Location"])
        self.assertEqual(public_response.status_code, 200, "Published slide URL not working at all")
        self.assertIn("text/html", public_response["Content-Type"])
        self.assertIn(event.name, public_response.content.decode("utf-8"))
        self.assertIn("slidesCarousel", public_response.content.decode("utf-8"))
        self.assertIn("carousel-item", public_response.content.decode("utf-8"))
        self.assertIn("result_presentation_mode", public_response.context)
        self.assertIn("show_types", public_response.context)
        self.assertEqual(public_response.context["event_name"], event.name)
        self.assertTrue(
                len(public_response.context["slides"]) > 0,
                "Published slide URL did not include any AKs",
        )

    def test_slide_export_web_view_invalid_config_redirects_to_export(self):
        """Invalid signed carousel configs should send users back to the export page."""
        event = Event.objects.get(slug="kif42")
        public_url = reverse_lazy("model:ak_slides_public", kwargs={"event_slug": "kif42"})
        response = self.client.get(f"{public_url}?config=definitely-not-a-valid-signature")

        self.assertEqual(response.status_code, 302, "Invalid slide config did not redirect")
        expected_redirect = str(reverse_lazy("admin:ak_slide_export", kwargs={"event_slug": event.slug}))
        self.assertEqual(response["Location"], expected_redirect)

    def test_slide_export_pdf(self):
        """
        Test PDF export based on the web carousel
        This ensures the export redirects to a public print view containing one page per slide of the web carousel.
        """
        self.client.force_login(self.admin_user)
        event = Event.objects.get(slug="kif42")
        export_url = reverse_lazy("admin:ak_slide_export", kwargs={"event_slug": "kif42"})
        data = self._slide_export_base_data(event)

        response = self.client.post(export_url, data={**data, "export_mode": "pdf"})
        self.assertEqual(response.status_code, 302, "PDF slide export did not redirect to the print view")
        pdf_url = str(reverse_lazy("model:ak_slides_pdf", kwargs={"event_slug": "kif42"}))
        self.assertTrue(response["Location"].startswith(pdf_url),
                        msg=f"Unexpected redirect target: {response['Location']}")

        self.client.logout()
        pdf_response = self.client.get(response["Location"])
        self.assertEqual(pdf_response.status_code, 200, "Slide print view not working at all")
        content = pdf_response.content.decode("utf-8")
        self.assertIn("window.print()", content)

        # Compare with the slides of the web carousel for the same configuration
        self.client.force_login(self.admin_user)
        web_response = self.client.post(export_url, data={**data, "export_mode": "web"})
        slides = self.client.get(web_response["Location"]).context["slides"]
        self.assertEqual(content.count('class="pdf-slide"'), len(slides),
                         "Slide print view should contain one page per slide")
        for slide in slides:
            if slide["kind"] == "ak":
                self.assertIn(slide["ak"].name, content)

    def test_slide_export_pdf_invalid_config_redirects_to_export(self):
        """Invalid signed configs for the slide print view should send users back to the export page."""
        pdf_url = reverse_lazy("model:ak_slides_pdf", kwargs={"event_slug": "kif42"})
        response = self.client.get(f"{pdf_url}?config=definitely-not-a-valid-signature")
        self.assertEqual(response.status_code, 302, "Invalid slide config did not redirect")
        self.assertEqual(response["Location"],
                         str(reverse_lazy("admin:ak_slide_export", kwargs={"event_slug": "kif42"})))

    def test_slide_export_modes_include_expected_ak_count_for_configurations(self):
        """Both web and PDF exports include the expected number of AKs for multiple filter configurations."""
        self.client.force_login(self.admin_user)
        event = Event.objects.get(slug="kif42")
        export_url = reverse_lazy("admin:ak_slide_export", kwargs={"event_slug": "kif42"})
        primary_type, secondary_type = self._prepare_types_for_export_tests(event)

        configurations = [
            {
                "name": "all_default",
                "num_next": 3,
                "presentation_mode": False,
                "categories": [str(category.pk) for category in event.akcategory_set.all()],
                "types": [str(ak_type.pk) for ak_type in event.aktype_set.all()],
                "types_all_selected_only": False,
                "include_wishes": True,
            },
            {
                "name": "presentation_only",
                "num_next": 2,
                "presentation_mode": True,
                "categories": [str(category.pk) for category in event.akcategory_set.all()],
                "types": [str(ak_type.pk) for ak_type in event.aktype_set.all()],
                "types_all_selected_only": False,
                "include_wishes": True,
            },
            {
                "name": "single_category",
                "num_next": 1,
                "presentation_mode": False,
                "categories": [str(event.akcategory_set.get(pk=4).pk)],
                "types": [str(ak_type.pk) for ak_type in event.aktype_set.all()],
                "types_all_selected_only": False,
                "include_wishes": True,
            },
            {
                "name": "single_type",
                "num_next": 3,
                "presentation_mode": False,
                "categories": [str(category.pk) for category in event.akcategory_set.all()],
                "types": [str(primary_type.pk)],
                "types_all_selected_only": False,
                "include_wishes": True,
            },
            {
                "name": "all_selected_types_only",
                "num_next": 3,
                "presentation_mode": False,
                "categories": [str(category.pk) for category in event.akcategory_set.all()],
                "types": [str(primary_type.pk), str(secondary_type.pk)],
                "types_all_selected_only": True,
                "include_wishes": True,
            },
            {
                "name": "no_wishes",
                "num_next": 3,
                "presentation_mode": False,
                "categories": [str(category.pk) for category in event.akcategory_set.all()],
                "types": [str(ak_type.pk) for ak_type in event.aktype_set.all()],
                "types_all_selected_only": False,
                "include_wishes": False,
            },
            {
                "name": "presentation_only_without_wishes",
                "num_next": 3,
                "presentation_mode": True,
                "categories": [str(category.pk) for category in event.akcategory_set.all()],
                "types": [str(ak_type.pk) for ak_type in event.aktype_set.all()],
                "types_all_selected_only": False,
                "include_wishes": False,
            },
        ]

        for config in configurations:
            expected_count = self._expected_slide_ak_count(event, config)

            web_data = {
                "num_next": config["num_next"],
                "presentation_mode": str(config["presentation_mode"]),
                "include_wishes": str(config["include_wishes"]),
                "export_mode": "web",
                "categories": config["categories"],
                "types": config["types"],
            }
            if config["types_all_selected_only"]:
                web_data["types_all_selected_only"] = "on"

            web_response = self.client.post(export_url, data=web_data)
            self.assertEqual(web_response.status_code, 302, msg=f"{config['name']}: web export did not redirect")
            self.client.logout()
            published_response = self.client.get(web_response["Location"])
            self.client.force_login(self.admin_user)
            self.assertEqual(
                    len([slide for slide in published_response.context["slides"] if slide["kind"] == "ak"]),
                    expected_count,
                    msg=f"{config['name']}: wrong AK count in web export",
            )

            pdf_data = {
                "num_next": config["num_next"],
                "presentation_mode": str(config["presentation_mode"]),
                "include_wishes": str(config["include_wishes"]),
                "export_mode": "pdf",
                "categories": config["categories"],
                "types": config["types"],
            }
            if config["types_all_selected_only"]:
                pdf_data["types_all_selected_only"] = "on"

            pdf_response = self.client.post(export_url, data=pdf_data)
            self.assertEqual(pdf_response.status_code, 302, msg=f"{config['name']}: pdf export did not redirect")
            self.client.logout()
            print_response = self.client.get(pdf_response["Location"])
            self.client.force_login(self.admin_user)
            self.assertEqual(
                    len([slide for slide in print_response.context["slides"] if slide["kind"] == "ak"]),
                    expected_count,
                    msg=f"{config['name']}: wrong AK count in pdf export",
            )

    def _slide_export_base_data(self, event):
        """Create form data for the slide export including all categories and types of the given event."""
        data = {
            "num_next": 3,
            "presentation_mode": "False",
            "include_wishes": "True",
            "categories": [str(category.pk) for category in event.akcategory_set.all()],
        }
        if event.aktype_set.exists():
            data["types"] = [str(ak_type.pk) for ak_type in event.aktype_set.all()]
        return data

    def _run_slide_exports(self, data):
        """
        Run web and PDF slide export with the given form data

        :return: tuple of the responses of the published web slides and the print view used to create the PDF
        """
        export_url = reverse_lazy("admin:ak_slide_export", kwargs={"event_slug": "kif42"})

        web_response = self.client.post(export_url, data={**data, "export_mode": "web"})
        self.assertEqual(web_response.status_code, 302, "Web slide export did not redirect")
        published_response = self.client.get(web_response["Location"])
        self.assertEqual(published_response.status_code, 200, "Published slides not working")

        pdf_response = self.client.post(export_url, data={**data, "export_mode": "pdf"})
        self.assertEqual(pdf_response.status_code, 302, "PDF slide export did not redirect")
        print_response = self.client.get(pdf_response["Location"])
        self.assertEqual(print_response.status_code, 200, "Slide print view not working")

        return published_response, print_response

    def test_slide_export_timespan_defaults_to_event(self):
        """
        The timespan is one grouped field with two date pickers (start and end) and a joint label,
        it defaults to start and end of the event (in its timezone).
        """
        self.client.force_login(self.admin_user)
        event = Event.objects.get(slug="kif42")
        export_url = reverse_lazy("admin:ak_slide_export", kwargs={"event_slug": "kif42"})

        response = self.client.get(export_url)
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial["timespan"], (event.start, event.end))

        content = response.content.decode("utf-8")
        self.assertEqual(content.count('type="datetime-local"'), 2, "Timespan fields do not use a date picker")
        self.assertIn('name="timespan_0"', content)
        self.assertIn('name="timespan_1"', content)
        # Django does not link labels of multi widgets to a single input, the inputs have aria-labels instead
        self.assertEqual(content.count('<label class="form-label">Timespan</label>'), 1,
                         "Timespan inputs do not share one label")
        self.assertIn('aria-label="Timespan start"', content)
        self.assertIn('aria-label="Timespan end"', content)
        self.assertIn('timespan-widget', content, "Timespan inputs not grouped")
        # Event starts 2020-11-06T17:51:26Z and ends 2020-11-10T17:51:27Z, i.e., 18:51 in Europe/Berlin
        self.assertIn('value="2020-11-06T18:51"', content, "Timespan start not prefilled with event start")
        self.assertIn('value="2020-11-10T18:51"', content, "Timespan end not prefilled with event end")

    def test_slide_export_timespan_filters_aks(self):
        """
        Only AKs with at least one slot overlapping the chosen timespan are included in web and PDF export,
        the chosen timespan is shown on the title page (in simplified format) if it deviates from the event's timespan.

        Slots of kif42 (Europe/Berlin): AK 1 Fri 19:30-21:30, AK 2 Sun 13:30-15:30, AK 3 unscheduled,
        AK 4 Sat 17:00-19:00 and Sun 19:30-21:30. The event ends Tue 18:51.
        AK 3 is a wish and hence included independent of the timespan (since wishes are included).
        """
        self.client.force_login(self.admin_user)
        event = Event.objects.get(slug="kif42")
        base_data = self._slide_export_base_data(event)

        configurations = [
            {
                "name": "default_timespan_includes_unscheduled",
                "timespan_start": "2020-11-06T18:51",
                "timespan_end": "2020-11-10T18:51",
                "expected_aks": {1, 2, 3, 4},
                "expected_timespan": "",
            },
            {
                "name": "empty_timespan_uses_default",
                "timespan_start": "",
                "timespan_end": "",
                "expected_aks": {1, 2, 3, 4},
                "expected_timespan": "",
            },
            {
                "name": "sunday",
                "timespan_start": "2020-11-08T00:00",
                "timespan_end": "2020-11-08T23:59",
                "expected_aks": {2, 3, 4},
                "expected_timespan": "Timespan: Sun 0:00 - Sun 23:59",
            },
            {
                "name": "saturday",
                "timespan_start": "2020-11-07T00:00",
                "timespan_end": "2020-11-07T23:59",
                "expected_aks": {3, 4},
                "expected_timespan": "Timespan: Sat 0:00 - Sat 23:59",
            },
            {
                "name": "partial_overlap",
                "timespan_start": "2020-11-06T21:00",
                "timespan_end": "2020-11-06T22:00",
                "expected_aks": {1, 3},
                "expected_timespan": "Timespan: Fri 21:00 - Fri 22:00",
            },
            {
                "name": "only_touching_slot_start",
                "timespan_start": "2020-11-06T18:00",
                "timespan_end": "2020-11-06T19:30",
                "expected_aks": {3},
                "expected_timespan": "Timespan: Fri 18:00 - Fri 19:30",
            },
            {
                "name": "only_start_given_ends_with_event",
                "timespan_start": "2020-11-08T00:00",
                "timespan_end": "",
                "expected_aks": {2, 3, 4},
                "expected_timespan": "Timespan: Sun 0:00 - Tue 18:51",
            },
        ]

        for config in configurations:
            published_response, print_response = self._run_slide_exports({
                **base_data,
                "timespan_0": config["timespan_start"],
                "timespan_1": config["timespan_end"],
            })

            web_aks = {slide["ak"].pk for slide in published_response.context["slides"] if slide["kind"] == "ak"}
            self.assertEqual(web_aks, config["expected_aks"], msg=f"{config['name']}: wrong AKs in web export")
            pdf_aks = {slide["ak"].pk for slide in print_response.context["slides"] if slide["kind"] == "ak"}
            self.assertEqual(pdf_aks, config["expected_aks"], msg=f"{config['name']}: wrong AKs in pdf export")

            title_slide = published_response.context["slides"][0]
            self.assertEqual(title_slide["kind"], "title")
            self.assertEqual(title_slide["timespan"], config["expected_timespan"],
                             msg=f"{config['name']}: wrong timespan on web title slide")
            self.assertEqual(print_response.context["slides"][0]["timespan"], config["expected_timespan"],
                             msg=f"{config['name']}: wrong timespan on pdf title slide")
            if config["expected_timespan"]:
                self.assertIn(config["expected_timespan"], published_response.content.decode("utf-8"),
                              msg=f"{config['name']}: timespan not rendered on web title slide")

    def test_slide_export_include_wishes_independent_of_other_settings(self):
        """
        Wishes are included or excluded only depending on the explicit wish setting,
        neither presentation mode nor timespan influence whether wishes are shown.

        AK 3 is the only wish of kif42 (unscheduled), AKs 1 and 4 should be presented, AK 2 is set to not be presented.
        """
        self.client.force_login(self.admin_user)
        event = Event.objects.get(slug="kif42")
        wish = AK.objects.get(pk=3)
        self.assertTrue(wish.wish)
        # Make sure the wish would be excluded if presentation mode influenced wishes
        wish.present = False
        wish.save()
        # Make sure presentation mode excludes at least one AK that is not a wish
        AK.objects.filter(pk=2).update(present=False)

        configurations: list[dict[str, Any]] = [
            {"name": "wishes_default", "include_wishes": "True", "presentation_mode": "False",
             "timespan": ("", ""), "expected_aks": {1, 2, 3, 4}},
            {"name": "no_wishes_default", "include_wishes": "False", "presentation_mode": "False",
             "timespan": ("", ""), "expected_aks": {1, 2, 4}},
            {"name": "wishes_presentation", "include_wishes": "True", "presentation_mode": "True",
             "timespan": ("", ""), "expected_aks": {1, 3, 4}},
            {"name": "no_wishes_presentation", "include_wishes": "False", "presentation_mode": "True",
             "timespan": ("", ""), "expected_aks": {1, 4}},
            {"name": "wishes_timespan", "include_wishes": "True", "presentation_mode": "False",
             "timespan": ("2020-11-08T00:00", "2020-11-08T23:59"), "expected_aks": {2, 3, 4}},
            {"name": "no_wishes_timespan", "include_wishes": "False", "presentation_mode": "False",
             "timespan": ("2020-11-08T00:00", "2020-11-08T23:59"), "expected_aks": {2, 4}},
        ]

        for config in configurations:
            published_response, print_response = self._run_slide_exports({
                **self._slide_export_base_data(event),
                "include_wishes": config["include_wishes"],
                "presentation_mode": config["presentation_mode"],
                "timespan_0": config["timespan"][0],
                "timespan_1": config["timespan"][1],
            })
            for response, mode in [(published_response, "web"), (print_response, "pdf")]:
                aks = {slide["ak"].pk for slide in response.context["slides"] if slide["kind"] == "ak"}
                self.assertEqual(aks, config["expected_aks"], msg=f"{config['name']}: wrong AKs in {mode} export")

    def test_slide_export_timespan_end_before_start_invalid(self):
        """A timespan ending before (or at) its start is rejected."""
        self.client.force_login(self.admin_user)
        event = Event.objects.get(slug="kif42")
        export_url = reverse_lazy("admin:ak_slide_export", kwargs={"event_slug": "kif42"})

        for timespan_end in ["2020-11-07T23:00", "2020-11-08T00:00"]:
            response = self.client.post(export_url, data={
                **self._slide_export_base_data(event),
                "export_mode": "web",
                "timespan_0": "2020-11-08T00:00",
                "timespan_1": timespan_end,
            })
            self.assertEqual(response.status_code, 200, "Invalid timespan did not re-render the form")
            self.assertIn("timespan", response.context["form"].errors)

    def test_slide_export_web_view_config_without_timespan(self):
        """Signed carousel configs created before the timespan filter existed still include all AKs."""
        event = Event.objects.get(slug="kif42")
        config = signing.dumps({
            "num_next": 3,
            "presentation_mode": False,
            "types": [str(ak_type.pk) for ak_type in event.aktype_set.all()],
            "types_all_selected_only": False,
            "categories": [str(category.pk) for category in event.akcategory_set.all()],
        })
        public_url = reverse_lazy("model:ak_slides_public", kwargs={"event_slug": "kif42"})

        response = self.client.get(f"{public_url}?{urlencode({'config': config})}")
        self.assertEqual(response.status_code, 200)
        web_aks = {slide["ak"].pk for slide in response.context["slides"] if slide["kind"] == "ak"}
        self.assertEqual(web_aks, set(AK.objects.filter(event=event).values_list("pk", flat=True)))
        self.assertEqual(response.context["slides"][0]["timespan"], "")

    def test_list_api_views(self):
        """
        Test list API views, checking whether they load correctly
        and include the correct items and fields
        """
        api_views: list[tuple[str, Any, Any]] = [
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

    def test_cv_mark_resolved_with_reason(self):
        """
        Test that marking constraint violations as resolved stores the (optional) reason and the user
        """
        self.client.force_login(self.admin_user)
        url = reverse('admin:cv-mark-resolved')

        # Confirmation page asks for the reason
        response = self.client.get(url, {'pks': '1,2'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('resolution_reason', response.context['form'].fields)

        response = self.client.post(f"{url}?pks=1,2", {'pks': '1,2', 'resolution_reason': 'Discussed with AK owners'})
        self.assertRedirects(response, reverse('admin:AKModel_constraintviolation_changelist'))
        for cv in ConstraintViolation.objects.filter(pk__in=[1, 2]):
            self.assertTrue(cv.manually_resolved)
            self.assertEqual(cv.resolution_reason, 'Discussed with AK owners')
            self.assertEqual(cv.resolved_by, self.admin_user)
        self.assertFalse(ConstraintViolation.objects.get(pk=3).manually_resolved)

        # Reason is optional
        response = self.client.post(f"{url}?pks=3", {'pks': '3'})
        self.assertRedirects(response, reverse('admin:AKModel_constraintviolation_changelist'))
        cv = ConstraintViolation.objects.get(pk=3)
        self.assertTrue(cv.manually_resolved)
        self.assertEqual(cv.resolution_reason, '')
        self.assertEqual(cv.resolved_by, self.admin_user)

    def test_cv_mark_resolved_redirects_to_next(self):
        """
        Test that marking constraint violations as resolved returns to the page given as "next" (if it is local)
        """
        self.client.force_login(self.admin_user)
        url = reverse('admin:cv-mark-resolved')
        cv_list_url = reverse('admin:constraint-violations', kwargs={'slug': 'kif42'})

        response = self.client.post(f"{url}?pks=1&next={cv_list_url}", {'pks': '1'})
        self.assertRedirects(response, cv_list_url)
        self.assertTrue(ConstraintViolation.objects.get(pk=1).manually_resolved)

        # External URLs are ignored
        response = self.client.post(f"{url}?pks=2&next=https://example.com/", {'pks': '2'})
        self.assertRedirects(response, reverse('admin:AKModel_constraintviolation_changelist'))

    def test_status_page_requirement_counts(self):
        """
        Test that the requirements widget on the status page shows (and links) the number of AKs (excluding trashed
        ones) and rooms having each requirement
        """
        self.client.force_login(self.admin_user)
        event = Event.objects.get(slug="kif42")
        AK.objects.get(pk=4).move_to_trash()
        ak_list_url = reverse('admin:AKModel_ak_changelist')
        room_list_url = reverse('admin:AKModel_room_changelist')

        response = self.client.get(reverse('admin:event_status', kwargs={'event_slug': event.slug}))
        for requirement_pk, ak_count, room_count in [(3, 1, 1), (4, 1, 1), (5, 0, 0)]:
            self.assertContains(
                    response,
                    f'href="{ak_list_url}?event__id__exact={event.pk}&requirements__id__exact={requirement_pk}'
                    f'&trashed=NOT_TRASHED">{ak_count}</a>')
            self.assertContains(
                    response,
                    f'href="{room_list_url}?event__id__exact={event.pk}&properties__id__exact={requirement_pk}">'
                    f'{room_count}</a>')

        # The linked admin lists show exactly the counted entities
        params: dict[str, Any] = {'event__id__exact': event.pk, 'requirements__id__exact': 3, 'trashed': 'NOT_TRASHED'}
        response = self.client.get(ak_list_url, params)
        self.assertEqual(response.context['cl'].result_count, 1)
        response = self.client.get(room_list_url, {'event__id__exact': event.pk, 'properties__id__exact': 3})
        self.assertEqual(response.context['cl'].result_count, 1)

    def test_orga_messages_status_widget_and_mark_resolved(self):
        """
        Test that the status page only lists unresolved orga messages (and counts the resolved ones)
        and that messages can be marked as resolved from there
        """
        self.client.force_login(self.admin_user)
        event = Event.objects.get(slug="kif42")
        ak = event.ak_set.first()
        assert ak is not None
        open_message = AKOrgaMessage.objects.create(ak=ak, event=event, text="Open orga message")
        AKOrgaMessage.objects.create(ak=ak, event=event, text="Resolved orga message", resolved=True)
        status_url = reverse('admin:event_status', kwargs={'event_slug': event.slug})
        mark_resolved_url = reverse('admin:akorgamessage-mark-resolved')
        resolved_list_url = (f"{reverse('admin:AKModel_akorgamessage_changelist')}"
                             f"?ak__event__id__exact={event.pk}&resolved__exact=1")

        response = self.client.get(status_url)
        self.assertContains(response, "Open orga message")
        self.assertNotContains(response, "Resolved orga message")
        self.assertContains(response, f"{mark_resolved_url}?pks={open_message.pk}&next={status_url}")
        self.assertRegex(response.content.decode(), rf'href="{re.escape(resolved_list_url)}">\s*1\s*</a>')

        # Confirmation page shows the message
        response = self.client.get(mark_resolved_url, {'pks': open_message.pk})
        self.assertContains(response, "Open orga message")

        response = self.client.post(f"{mark_resolved_url}?pks={open_message.pk}&next={status_url}",
                                    {'pks': open_message.pk})
        self.assertRedirects(response, status_url)
        open_message.refresh_from_db()
        self.assertTrue(open_message.resolved)

        response = self.client.get(status_url)
        self.assertNotContains(response, "Open orga message")
        self.assertRegex(response.content.decode(), rf'href="{re.escape(resolved_list_url)}">\s*2\s*</a>')


class EventShiftDatesTests(BasicViewTests, TestCase):
    """
    Tests for shifting all dates of an event (debugging functionality)
    """

    fixtures = ["model.json"]

    def test_event_shift_dates_unavailable_without_debug(self):
        """
        Test that shifting event dates (debugging functionality) is neither offered nor reachable without DEBUG
        (the test runner always uses DEBUG=False)
        """
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('admin:AKModel_event_changelist'))
        actions = [a for a, _ in response.context['action_form'].fields['action'].choices]
        self.assertNotIn('shift_dates', actions)

        response = self.client.get(reverse('admin:event-shift-dates'), {'pks': '2'})
        self.assertEqual(response.status_code, 404)

    @staticmethod
    def _date_snapshot():
        """
        Collect the dates of various models belonging to events

        :return: dict mapping (model label, pk, field name) to (event id, value)
        """
        snapshot = {}
        models_and_fields: list[tuple[Any, list[str]]] = [
            (AKSlot, ['start', 'updated']),
            (Availability, ['start', 'end']),
            (DefaultSlot, ['start', 'end']),
            (ConstraintViolation, ['timestamp']),
            (apps.get_model('AKModel', 'HistoricalAK'), ['history_date', 'trashed_at']),
        ]
        for model, fields in models_and_fields:
            for obj in model.objects.all():
                for field in fields:
                    snapshot[(model._meta.label, obj.pk, field)] = (obj.event_id, getattr(obj, field))
        return snapshot

    def _assert_snapshot_shifted(self, old_snapshot, event_pk, delta):
        """
        Assert that all dates belonging to the given event were shifted by delta and all others were not changed

        :param old_snapshot: snapshot before shifting (see :meth:`_date_snapshot`)
        :param event_pk: primary key of the shifted event
        :param delta: offset the event was shifted by
        """
        new_snapshot = self._date_snapshot()
        self.assertEqual(new_snapshot.keys(), old_snapshot.keys())
        for key, (event_id, old_value) in old_snapshot.items():
            expected = old_value + delta if event_id == event_pk and old_value is not None else old_value
            self.assertEqual(new_snapshot[key][1], expected, msg=f"{key} not shifted correctly")

    @override_settings(DEBUG=True)
    def test_event_shift_dates(self):
        """
        Test shifting an event and everything belonging to it to a new start date
        """
        self.client.force_login(self.admin_user)
        event = Event.objects.get(pk=2)
        old_event_values = {f: getattr(event, f) for f in ['start', 'end', 'reso_deadline', 'interest_start',
                                                           'interest_end', 'plan_published_at', 'poll_published_at']}
        old_other_event_start = Event.objects.get(pk=1).start
        old_snapshot = self._date_snapshot()
        changelist_url = reverse('admin:AKModel_event_changelist')
        url = reverse('admin:event-shift-dates')

        # Action is offered and redirects to the intermediate view
        response = self.client.get(changelist_url)
        self.assertIn('shift_dates', [a for a, _ in response.context['action_form'].fields['action'].choices])
        response = self.client.post(changelist_url, {'action': 'shift_dates', '_selected_action': ['2']})
        self.assertRedirects(response, f"{url}?pks=2")

        # Only one event at a time
        response = self.client.post(changelist_url, {'action': 'shift_dates', '_selected_action': ['1', '2']},
                                    follow=True)
        self._assert_message(response, "Dates can only be shifted for exactly one event at a time.")

        # Intermediate view shows the current start (in the timezone of the event)
        response = self.client.get(url, {'pks': '2'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].initial['new_start'], event.start)

        # Perform shift (new start is interpreted in the timezone of the event)
        new_start = datetime(2026, 11, 23, 9, 30, tzinfo=event.timezone)
        delta = new_start - event.start
        response = self.client.post(f"{url}?pks=2", {'pks': '2', 'new_start': '2026-11-23T09:30'})
        self.assertRedirects(response, changelist_url)

        event.refresh_from_db()
        self.assertEqual(event.start, new_start)
        for field, old_value in old_event_values.items():
            expected = old_value + delta if old_value is not None else None
            self.assertEqual(getattr(event, field), expected, msg=f"Event field {field} not shifted correctly")

        # Other events are not touched, everything belonging to the event is shifted, everything else not
        self.assertEqual(Event.objects.get(pk=1).start, old_other_event_start)
        self._assert_snapshot_shifted(old_snapshot, event.pk, delta)


class DefaultSlotEditorTests(BasicViewTests, TestCase):
    """
    Tests for saving default slots in the default slot editor
    """

    fixtures = ["model.json"]

    def setUp(self):
        super().setUp()
        self.event = Event.get_by_slug("kif42")
        self.start = self.event.start.astimezone(self.event.timezone).replace(tzinfo=None)

    def _slot(self, slot_id="", start_offset_hours=0, duration_hours=1):
        start = self.start + timedelta(hours=start_offset_hours)
        return {"id": slot_id, "start": start.isoformat(), "end": (start + timedelta(hours=duration_hours)).isoformat()}

    def _post(self, slots):
        self.client.force_login(self.admin_user)
        return self.client.post(
                reverse("admin:default-slots-editor", kwargs={"event_slug": self.event.slug}),
                {"availabilities": json.dumps({"availabilities": slots})},
        )

    def _assert_rejected(self, slots):
        """
        Assert that the submitted slots are rejected as a whole (editor shown again with an error, nothing changed)
        """
        slots_before = list(self.event.defaultslot_set.values_list("pk", "start", "end"))
        response = self._post(slots)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].has_error("availabilities"))
        self.assertEqual(list(self.event.defaultslot_set.values_list("pk", "start", "end")), slots_before)

    def test_invalid_date_rejected(self):
        """
        Test that an invalid date in one of the submitted slots is rejected before any slot is changed
        """
        self._assert_rejected([self._slot(), {"id": "", "start": "not a date", "end": self.start.isoformat()}])

    def test_invalid_id_rejected(self):
        """
        Test that an invalid id in one of the submitted slots is rejected before any slot is changed
        """
        self._assert_rejected([self._slot(), self._slot(slot_id="abc")])

    def test_end_before_start_rejected(self):
        """
        Test that slots not ending after their start are rejected
        """
        self._assert_rejected([self._slot(), self._slot(duration_hours=-1)])
        self._assert_rejected([self._slot(duration_hours=0)])

    def test_duplicate_id_rejected(self):
        """
        Test that submitting the same existing slot more than once is rejected
        """
        DefaultSlot.objects.create(event=self.event, start=self.event.start, end=self.event.start + timedelta(hours=1))
        slot_id = str(self.event.defaultslot_set.first().pk)
        self._assert_rejected([self._slot(slot_id=slot_id), self._slot(slot_id=slot_id, start_offset_hours=2)])

    def test_valid_slots_saved(self):
        """
        Test that valid submitted slots replace the existing default slots of the event
        """
        response = self._post([self._slot()])

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.event.defaultslot_set.count(), 1)
        self.assertEqual(self.event.defaultslot_set.get().start, self.event.start.astimezone(self.event.timezone))

    def test_existing_slot_updated(self):
        """
        Test that existing slots are updated (and not re-created) and others are deleted
        """
        kept = DefaultSlot.objects.create(event=self.event, start=self.event.start,
                                          end=self.event.start + timedelta(hours=1))
        DefaultSlot.objects.create(event=self.event, start=self.event.start + timedelta(hours=3),
                                   end=self.event.start + timedelta(hours=4))

        response = self._post([self._slot(slot_id=str(kept.pk), start_offset_hours=1, duration_hours=2)])

        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(self.event.defaultslot_set.values_list("pk", flat=True)), [kept.pk])
        kept.refresh_from_db()
        self.assertEqual(kept.end - kept.start, timedelta(hours=2))
