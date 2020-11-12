from django.contrib import admin

from AKModel.admin import RoomAdmin, RoomForm
from AKOnline.models import VirtualRoom


class VirtualRoomForm(RoomForm):
    class Meta(RoomForm.Meta):
        model = VirtualRoom
        fields = ['name',
                  'location',
                  'url',
                  'capacity',
                  'properties',
                  'event',
                  ]


@admin.register(VirtualRoom)
class VirtualRoomAdmin(RoomAdmin):
    model = VirtualRoom

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is not None:
            return VirtualRoomForm
        return super().get_form(request, obj, change, **kwargs)
