from django.contrib import admin
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from AKModel.availability.models import Availability
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
    actions = ['wiki_export']

    def is_wish(self, obj):
        return obj.wish

    def wiki_export(self, request, queryset):
        return render(request,
                      'admin/AKModel/wiki_export.html',
                      context={"AKs": queryset})
    wiki_export.short_description = _("Export to wiki syntax")

    is_wish.boolean = True


admin.site.register(AK, AKAdmin)

admin.site.register(Room)

admin.site.register(AKSlot)

admin.site.register(Availability)
