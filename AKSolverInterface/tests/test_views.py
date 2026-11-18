from django.test import TestCase

from AKModel.tests.test_views import BasicViewTests


class ModelViewTests(BasicViewTests, TestCase):
    """
    Tests for AKSolverInterface
    """

    fixtures = ["model.json"]

    VIEWS_STAFF_ONLY = [
        ("admin:scheduling_wizard_export", {"event_slug": "kif42"}),
        ("admin:scheduling_wizard_import", {"event_slug": "kif42"}),
    ]
