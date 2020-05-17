from django.contrib import admin

from AKModel.admin import RoomAdmin
from AKOnline.models import VirtualRoom


@admin.register(VirtualRoom)
class VirtualRoomAdmin(RoomAdmin):
    model = VirtualRoom
