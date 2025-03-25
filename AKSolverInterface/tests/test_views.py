from django.test import TestCase

from AKModel.tests.test_views import BasicViewTests


class ModelViewTests(BasicViewTests, TestCase):
    """
    Tests for AKSolverInterface
    """

    fixtures = ["model.json"]

    VIEWS_STAFF_ONLY = [
        ("admin:ak_json_export", {"event_slug": "kif42"}),
        ("admin:ak_schedule_json_import", {"event_slug": "kif42"}),
    ]
