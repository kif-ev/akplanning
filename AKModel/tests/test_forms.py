from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from AKModel.forms import RoomFormWithAvailabilities
from AKModel.models import AK, AKRequirement, AKSlot, Event, Room


class EventRestrictedFieldsFormMixinTests(TestCase):
    """
    Tests for restricting the choices of related fields to the event of the edited instance
    (configured via ``Meta.event_restricted_fields``)
    """
    fixtures = ['model.json']

    def setUp(self):
        self.event = Event.get_by_slug('kif42')
        self.other_event = Event.objects.exclude(pk=self.event.pk).first()
        # Ensure there are choices belonging to another event that have to be filtered out
        self.other_room = Room.objects.create(name="Other room", capacity=10, event=self.other_event)
        self.other_requirement = AKRequirement.objects.create(name="Other requirement", event=self.other_event)
        self.request = RequestFactory().get("/")
        self.request.user = get_user_model().objects.create(username="formadmin", is_staff=True, is_superuser=True)

    def test_admin_form(self):
        """
        Test that the setting is kept when the admin builds its form class (via modelform_factory)
        """
        slot = AKSlot.objects.filter(event=self.event).first()
        form_class = admin.site.get_model_admin(AKSlot).get_form(self.request, slot)
        form = form_class(instance=slot)

        self.assertNotIn(self.other_room, form.fields["room"].queryset)
        self.assertEqual(set(form.fields["room"].queryset), set(Room.objects.filter(event=self.event)))
        self.assertEqual(set(form.fields["ak"].queryset), set(AK.objects.filter(event=self.event)))

        # Without an event (e.g., when adding a new slot), choices are not restricted
        form = form_class()
        self.assertIn(self.other_room, form.fields["room"].queryset)

    def test_inherited_form(self):
        """
        Test restriction for a form combining the mixin with further form mixins and parent forms
        """
        room = Room.objects.filter(event=self.event).first()
        form = RoomFormWithAvailabilities(instance=room)
        self.assertNotIn(self.other_requirement, form.fields["properties"].queryset)
        self.assertEqual(set(form.fields["properties"].queryset), set(AKRequirement.objects.filter(event=self.event)))
