# Register your models here.

from django.contrib import admin

from AKModel.availability import Availability
from AKModel.models import Event, AKOwner, AKCategory, AKTrack, AKTag, AKRequirement, AK, Room, AKSlot

admin.site.register(Event)

admin.site.register(AKOwner)

admin.site.register(AKCategory)
admin.site.register(AKTrack)
admin.site.register(AKTag)
admin.site.register(AKRequirement)


class AKAdmin(admin.ModelAdmin):
    model = AK
    list_display = ['name', 'short_name', 'category', 'is_wish']

    def is_wish(self, obj):
        return obj.wish

    is_wish.boolean = True


admin.site.register(AK, AKAdmin)

admin.site.register(Room)

admin.site.register(AKSlot)

admin.site.register(Availability)
