from django.test import TestCase
from AKModel.tests import BasicViewTests


class ModelViewTests(BasicViewTests, TestCase):
    fixtures = ['model.json']

    VIEWS_STAFF_ONLY = [
        ('admin:schedule', {'event_slug': 'kif42'}),
        ('admin:slots_unscheduled', {'event_slug': 'kif42'}),
        ('admin:constraint-violations', {'slug': 'kif42'}),
        ('admin:special-attention', {'slug': 'kif42'}),
        ('admin:cleanup-wish-slots', {'event_slug': 'kif42'}),
        ('admin:autocreate-availabilities', {'event_slug': 'kif42'}),
        ('admin:tracks_manage', {'event_slug': 'kif42'}),
        ('admin:enter-interest', {'event_slug': 'kif42', 'pk': 1}),
    ]
