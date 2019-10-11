# Register your models here.

from django.contrib import admin

from AKModel.models import Event, AKOwner, AKType, AKTrack, AKTag, AKRequirement, AK, Room

admin.site.register(Event)

admin.site.register(AKOwner)

admin.site.register(AKType)
admin.site.register(AKTrack)
admin.site.register(AKTag)
admin.site.register(AKRequirement)
admin.site.register(AK)
admin.site.register(Room)
