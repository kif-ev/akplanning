from betterforms.multiform import MultiModelForm
from django.forms import ModelForm

from AKModel.forms import RoomForm
from AKOnline.models import VirtualRoom


class VirtualRoomForm(ModelForm):
    class Meta:
        model = VirtualRoom
        exclude = ['room']

    def __init__(self, *args, **kwargs):
        super(VirtualRoomForm, self).__init__(*args, **kwargs)
        self.fields['url'].required = False


class RoomWithVirtualForm(MultiModelForm):
    form_classes = {
        'room': RoomForm,
        'virtual': VirtualRoomForm
    }

    def save(self, commit=True):
        objects = super(RoomWithVirtualForm, self).save(commit=False)

        if commit:
            room = objects['room']
            room.save()

            virtual = objects['virtual']
            if virtual.url != "":
                virtual.room = room
                virtual.save()

        return objects
