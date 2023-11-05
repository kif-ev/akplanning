from betterforms.multiform import MultiModelForm
from django.forms import ModelForm

from AKModel.forms import RoomForm
from AKOnline.models import VirtualRoom


class VirtualRoomForm(ModelForm):
    """
    Form to create a virtual room

    Should be used as part of a multi form (see :class:`RoomWithVirtualForm` below)
    """
    class Meta:
        model = VirtualRoom
        # Show all fields except for room
        exclude = ['room'] #pylint: disable=modelform-uses-exclude

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make the URL field optional to allow submitting the multi form without creating a virtual room
        self.fields['url'].required = False


class RoomWithVirtualForm(MultiModelForm):
    """
    Combined form to create rooms and optionally virtual rooms

    Multi-Form that combines a :class:`RoomForm` (from AKModel) and a :class:`VirtualRoomForm` (see above).

    The form will always create a room on valid input
    and may additionally create a virtual room if the url field of the virtual room form part is set.
    """
    form_classes = {
        'room': RoomForm,
        'virtual': VirtualRoomForm
    }

    def save(self, commit=True):
        objects = super().save(commit=False)

        if commit:
            room = objects['room']
            room.save()

            virtual = objects['virtual']
            if virtual.url != "":
                virtual.room = room
                virtual.save()
            else:
                objects['virtual'] = None

        return objects
