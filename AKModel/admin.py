from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.db.models import Count, F
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from AKModel.availability import Availability
from AKModel.models import Event, AKOwner, AKCategory, AKTrack, AKTag, AKRequirement, AK, Room, AKSlot


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    def get_form(self, request, obj=None, change=False, **kwargs):
        # Use timezone of event
        if obj is not None and obj.timezone:
            timezone.activate(obj.timezone)
        # No timezone available? Use UTC
        else:
            timezone.activate("UTC")
        return super().get_form(request, obj, change, **kwargs)

admin.site.register(AKOwner)

admin.site.register(AKCategory)
admin.site.register(AKTrack)
admin.site.register(AKTag)
admin.site.register(AKRequirement)


class WishFilter(SimpleListFilter):
  title = _("Wish") # a label for our filter
  parameter_name = 'wishes' # you can put anything here

  def lookups(self, request, model_admin):
    # This is where you create filter options; we have two:
    return [
        ('WISH', _("Is wish")),
        ('NO_WISH', _("Is not a wish")),
    ]

  def queryset(self, request, queryset):
      annotated_queryset = queryset.annotate(owner_count=Count(F('owners')))
      if self.value() == 'NO_WISH':
          return annotated_queryset.filter(owner_count__gt=0)
      if self.value() == 'WISH':
          return annotated_queryset.filter(owner_count=0)
      return queryset


class AKAdmin(admin.ModelAdmin):
    model = AK
    list_display = ['name', 'short_name', 'category', 'is_wish']
    actions = ['wiki_export']
    list_filter = ['category', WishFilter]
    ordering = ['pk']

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


@admin.register(AKSlot)
class AKSlotAdmin(admin.ModelAdmin):
    def get_form(self, request, obj=None, change=False, **kwargs):
        # Use timezone of associated event
        if obj is not None and obj.event.timezone:
            timezone.activate(obj.event.timezone)
        # No timezone available? Use UTC
        else:
            timezone.activate("UTC")
        return super().get_form(request, obj, change, **kwargs)


@admin.register(Availability)
class AvailabilityAdmin(admin.ModelAdmin):
    def get_form(self, request, obj=None, change=False, **kwargs):
        # Use timezone of associated event
        if obj is not None and obj.event.timezone:
            timezone.activate(obj.event.timezone)
        # No timezone available? Use UTC
        else:
            timezone.activate("UTC")
        return super().get_form(request, obj, change, **kwargs)
