from django.apps import apps
from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.db.models import Count, F
from django.shortcuts import render
from django.urls import path, reverse_lazy
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from simple_history.admin import SimpleHistoryAdmin

from AKModel.availability.models import Availability
from AKModel.models import Event, AKOwner, AKCategory, AKTrack, AKTag, AKRequirement, AK, AKSlot, Room
from AKModel.views import EventStatusView


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    model = Event
    list_display = ['name', 'status_url', 'place', 'start', 'end', 'active']
    list_filter = ['active']
    list_editable = ['active']
    ordering = ['-start']

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<slug:slug>/status/', self.admin_site.admin_view(EventStatusView.as_view()), name="event_status")
        ]
        return custom_urls + urls

    def status_url(self, obj):
        return format_html("<a href='{url}'>{text}</a>",
                           url=reverse_lazy('admin:event_status', kwargs={'slug': obj.slug}), text=_("Status"))
    status_url.short_description = text=_("Status")

    def get_form(self, request, obj=None, change=False, **kwargs):
        # Use timezone of event
        if obj is not None and obj.timezone:
            timezone.activate(obj.timezone)
        # No timezone available? Use UTC
        else:
            timezone.activate("UTC")
        return super().get_form(request, obj, change, **kwargs)


@admin.register(AKOwner)
class AKOwnerAdmin(admin.ModelAdmin):
    model = AKOwner
    list_display = ['name', 'institution', 'event']
    list_filter = ['institution', 'event']
    list_editable = []
    ordering = ['name']

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'event':
            kwargs['initial'] = Event.get_next_active()
        return super(AKOwnerAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(AKCategory)
class AKCategoryAdmin(admin.ModelAdmin):
    model = AKCategory
    list_display = ['name', 'color', 'event']
    list_filter = ['event']
    list_editable = ['color']
    ordering = ['name']

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'event':
            kwargs['initial'] = Event.get_next_active()
        return super(AKCategoryAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(AKTrack)
class AKTrackAdmin(admin.ModelAdmin):
    model = AKTrack
    list_display = ['name', 'color', 'event']
    list_filter = ['event']
    list_editable = ['color']
    ordering = ['name']

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'event':
            kwargs['initial'] = Event.get_next_active()
        return super(AKTrackAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(AKTag)
class AKTagAdmin(admin.ModelAdmin):
    model = AKTag
    list_display = ['name']
    list_filter = []
    list_editable = []
    ordering = ['name']


@admin.register(AKRequirement)
class AKRequirementAdmin(admin.ModelAdmin):
    model = AKRequirement
    list_display = ['name', 'event']
    list_filter = ['event']
    list_editable = []
    ordering = ['name']

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'event':
            kwargs['initial'] = Event.get_next_active()
        return super(AKRequirementAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)


class WishFilter(SimpleListFilter):
    title = _("Wish")  # a label for our filter
    parameter_name = 'wishes'  # you can put anything here

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


@admin.register(AK)
class AKAdmin(SimpleHistoryAdmin):
    model = AK
    list_display = ['name', 'short_name', 'category', 'track', 'is_wish', 'interest', 'event']
    list_filter = ['category', WishFilter, 'event']
    list_editable = ['short_name', 'track', 'interest']
    ordering = ['pk']
    actions = ['wiki_export']

    def is_wish(self, obj):
        return obj.wish

    def wiki_export(self, request, queryset):
        return render(request, 'admin/AKModel/wiki_export.html', context={"AKs": queryset})

    wiki_export.short_description = _("Export to wiki syntax")

    is_wish.boolean = True

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'event':
            kwargs['initial'] = Event.get_next_active()
        return super(AKAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    model = Room
    list_display = ['name', 'location', 'capacity', 'event']
    list_filter = ['location', 'properties', 'event']
    list_editable = []
    ordering = ['location', 'name']

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'event':
            kwargs['initial'] = Event.get_next_active()
        return super(RoomAdmin, self).formfield_for_foreignkey(
            db_field, request, **kwargs
        )


@admin.register(AKSlot)
class AKSlotAdmin(admin.ModelAdmin):
    model = AKSlot
    list_display = ['id', 'ak', 'room', 'start', 'duration', 'event']
    list_filter = ['room', 'event']
    list_editable = ['ak', 'room', 'start', 'duration']
    ordering = ['start']

    readonly_fields = ['updated']

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = []
        if apps.is_installed("AKScheduling"):
            from AKScheduling.views import UnscheduledSlotsAdminView

            custom_urls.extend([
                path('<slug:event_slug>/unscheduled/', self.admin_site.admin_view(UnscheduledSlotsAdminView.as_view()),
                     name="slots_unscheduled")
            ])
        return custom_urls + urls

    def get_form(self, request, obj=None, change=False, **kwargs):
        # Use timezone of associated event
        if obj is not None and obj.event.timezone:
            timezone.activate(obj.event.timezone)
        # No timezone available? Use UTC
        else:
            timezone.activate("UTC")
        return super().get_form(request, obj, change, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'event':
            kwargs['initial'] = Event.get_next_active()
        return super(AKSlotAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)


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
