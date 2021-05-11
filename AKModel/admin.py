from django import forms
from django.apps import apps
from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.db.models import Count, F
from django.shortcuts import render, redirect
from django.urls import path, reverse_lazy
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from rest_framework.reverse import reverse
from simple_history.admin import SimpleHistoryAdmin

from AKModel.availability.forms import AvailabilitiesFormMixin
from AKModel.availability.models import Availability
from AKModel.models import Event, AKOwner, AKCategory, AKTrack, AKTag, AKRequirement, AK, AKSlot, Room, AKOrgaMessage, \
    ConstraintViolation
from AKModel.views import EventStatusView, AKCSVExportView, AKWikiExportView, AKMessageDeleteView, \
    AKRequirementOverview, \
    NewEventWizardStartView, NewEventWizardSettingsView, NewEventWizardPrepareImportView, NewEventWizardFinishView, \
    NewEventWizardImportView, NewEventWizardActivateView
from AKModel.views import export_slides


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    model = Event
    list_display = ['name', 'status_url', 'place', 'start', 'end', 'active']
    list_filter = ['active']
    list_editable = ['active']
    ordering = ['-start']

    def add_view(self, request, form_url='', extra_context=None):
        # Always use wizard to create new events
        # (the built-in form wouldn't work anyways since the timezone cannot be specified before starting to fill the form)
        return redirect("admin:new_event_wizard_start")

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('add/wizard/start/', self.admin_site.admin_view(NewEventWizardStartView.as_view()),
                 name="new_event_wizard_start"),
            path('add/wizard/settings/', self.admin_site.admin_view(NewEventWizardSettingsView.as_view()),
                 name="new_event_wizard_settings"),
            path('add/wizard/created/<slug:event_slug>/', self.admin_site.admin_view(NewEventWizardPrepareImportView.as_view()),
                 name="new_event_wizard_prepare_import"),
            path('add/wizard/import/<slug:event_slug>/from/<slug:import_slug>/',
                 self.admin_site.admin_view(NewEventWizardImportView.as_view()),
                 name="new_event_wizard_import"),
            path('add/wizard/activate/<slug:slug>/',
                 self.admin_site.admin_view(NewEventWizardActivateView.as_view()),
                 name="new_event_wizard_activate"),
            path('add/wizard/finish/<slug:slug>/',
                 self.admin_site.admin_view(NewEventWizardFinishView.as_view()),
                 name="new_event_wizard_finish"),
            path('<slug:slug>/status/', self.admin_site.admin_view(EventStatusView.as_view()), name="event_status"),
            path('<slug:event_slug>/requirements/', self.admin_site.admin_view(AKRequirementOverview.as_view()), name="event_requirement_overview"),
            path('<slug:event_slug>/ak-csv-export/', self.admin_site.admin_view(AKCSVExportView.as_view()), name="ak_csv_export"),
            path('<slug:slug>/ak-wiki-export/', self.admin_site.admin_view(AKWikiExportView.as_view()), name="ak_wiki_export"),
            path('<slug:event_slug>/ak-slide-export/', export_slides, name="ak_slide_export"),
            path('<slug:slug>/delete-orga-messages/', self.admin_site.admin_view(AKMessageDeleteView.as_view()),
                 name="ak_delete_orga_messages"),
        ]
        return custom_urls + urls

    def status_url(self, obj):
        return format_html("<a href='{url}'>{text}</a>",
                           url=reverse_lazy('admin:event_status', kwargs={'slug': obj.slug}), text=_("Status"))
    status_url.short_description = text=_("Status")

    def get_form(self, request, obj=None, change=False, **kwargs):
        # Use timezone of event
        timezone.activate(obj.timezone)
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

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = []
        if apps.is_installed("AKScheduling"):
            from AKScheduling.views import TrackAdminView

            custom_urls.extend([
                path('<slug:event_slug>/manage/', self.admin_site.admin_view(TrackAdminView.as_view()),
                     name="tracks_manage"),
            ])
        return custom_urls + urls


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


class AKAdminForm(forms.ModelForm):
    class Meta:
        widgets = {
            'requirements': forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter possible values for foreign keys & m2m when event is specified
        if hasattr(self.instance, "event") and self.instance.event is not None:
            self.fields["category"].queryset = AKCategory.objects.filter(event=self.instance.event)
            self.fields["track"].queryset = AKTrack.objects.filter(event=self.instance.event)
            self.fields["owners"].queryset = AKOwner.objects.filter(event=self.instance.event)
            self.fields["requirements"].queryset = AKRequirement.objects.filter(event=self.instance.event)
            self.fields["conflicts"].queryset = AK.objects.filter(event=self.instance.event)
            self.fields["prerequisites"].queryset = AK.objects.filter(event=self.instance.event)


@admin.register(AK)
class AKAdmin(SimpleHistoryAdmin):
    model = AK
    list_display = ['name', 'short_name', 'category', 'track', 'is_wish', 'interest', 'event']
    list_filter = ['category', WishFilter, 'event']
    list_editable = ['short_name', 'track', 'interest']
    ordering = ['pk']
    actions = ['wiki_export']
    form = AKAdminForm

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


class RoomForm(AvailabilitiesFormMixin, forms.ModelForm):
    class Meta:
        model = Room
        fields = ['name',
                  'location',
                  'capacity',
                  'properties',
                  'event',
                  ]

        widgets = {
            'properties': forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        # Init availability mixin
        kwargs['initial'] = dict()
        super().__init__(*args, **kwargs)
        self.initial = {**self.initial, **kwargs['initial']}
        # Filter possible values for m2m when event is specified
        if hasattr(self.instance, "event") and self.instance.event is not None:
            self.fields["properties"].queryset = AKRequirement.objects.filter(event=self.instance.event)



@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    model = Room
    list_display = ['name', 'location', 'capacity', 'event']
    list_filter = ['location', 'properties', 'event']
    list_editable = []
    ordering = ['location', 'name']
    change_form_template = "admin/AKModel/room_change_form.html"

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is not None:
            return RoomForm
        return super().get_form(request, obj, change, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'event':
            kwargs['initial'] = Event.get_next_active()
        return super(RoomAdmin, self).formfield_for_foreignkey(
            db_field, request, **kwargs
        )


class AKSlotAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter possible values for foreign keys when event is specified
        if hasattr(self.instance, "event") and self.instance.event is not None:
            self.fields["ak"].queryset = AK.objects.filter(event=self.instance.event)
            self.fields["room"].queryset = Room.objects.filter(event=self.instance.event)


@admin.register(AKSlot)
class AKSlotAdmin(admin.ModelAdmin):
    model = AKSlot
    list_display = ['id', 'ak', 'room', 'start', 'duration', 'event']
    list_filter = ['room', 'event']
    ordering = ['start']
    readonly_fields = ['ak_details_link', 'updated']
    form = AKSlotAdminForm

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = []
        if apps.is_installed("AKScheduling"):
            from AKScheduling.views import SchedulingAdminView, UnscheduledSlotsAdminView

            custom_urls.extend([
                path('<slug:event_slug>/schedule/', self.admin_site.admin_view(SchedulingAdminView.as_view()),
                     name="schedule"),
                path('<slug:event_slug>/unscheduled/', self.admin_site.admin_view(UnscheduledSlotsAdminView.as_view()),
                     name="slots_unscheduled"),
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

    def ak_details_link(self, akslot):
        if apps.is_installed("AKScheduling") and akslot.ak is not None:
            link = f"<a href={reverse('submit:ak_detail', args=[akslot.event.slug, akslot.ak.pk])}>{str(akslot.ak)}</a>"
            return mark_safe(link)
        return "-"
    ak_details_link.short_description = _('AK Details')


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


@admin.register(AKOrgaMessage)
class AKOrgaMessageAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'ak', 'text']
    list_filter = ['ak__event']
    readonly_fields = ['timestamp', 'ak', 'text']


class ConstraintViolationAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter possible values for foreign keys & m2m when event is specified
        if hasattr(self.instance, "event") and self.instance.event is not None:
            self.fields["ak_owner"].queryset = AKOwner.objects.filter(event=self.instance.event)
            self.fields["room"].queryset = Room.objects.filter(event=self.instance.event)
            self.fields["requirement"].queryset = AKRequirement.objects.filter(event=self.instance.event)
            self.fields["category"].queryset = AKCategory.objects.filter(event=self.instance.event)
            self.fields["aks"].queryset = AK.objects.filter(event=self.instance.event)
            self.fields["ak_slots"].queryset = AKSlot.objects.filter(event=self.instance.event)


@admin.register(ConstraintViolation)
class ConstraintViolationAdmin(admin.ModelAdmin):
    list_display = ['type', 'level', 'get_details']
    list_filter = ['event']
    readonly_fields = ['timestamp']
    form = ConstraintViolationAdminForm
