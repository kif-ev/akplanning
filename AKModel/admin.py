from django import forms
from django.apps import apps
from django.contrib import admin, messages
from django.contrib.admin import SimpleListFilter, RelatedFieldListFilter, action, display
from django.db.models import Count, F
from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect
from django.urls import reverse_lazy, path
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from rest_framework.reverse import reverse
from simple_history.admin import SimpleHistoryAdmin

from AKModel.availability.forms import AvailabilitiesFormMixin
from AKModel.availability.models import Availability
from AKModel.models import Event, AKOwner, AKCategory, AKTrack, AKRequirement, AK, AKSlot, Room, AKOrgaMessage, \
    ConstraintViolation, DefaultSlot
from AKModel.urls import get_admin_urls_event_wizard, get_admin_urls_event
from AKModel.views import CVMarkResolvedView, CVSetLevelViolationView, CVSetLevelWarningView, AKResetInterestView, \
    AKResetInterestCounterView, PlanPublishView, PlanUnpublishView, DefaultSlotEditorView, RoomBatchCreationView


class EventRelatedFieldListFilter(RelatedFieldListFilter):
    def field_choices(self, field, request, model_admin):
        ordering = self.field_admin_ordering(field, request, model_admin)
        limit_choices = {}
        if "event__id__exact" in request.GET:
            limit_choices['event__id__exact'] = request.GET["event__id__exact"]
        return field.get_choices(include_blank=False, limit_choices_to=limit_choices, ordering=ordering)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    model = Event
    list_display = ['name', 'status_url', 'place', 'start', 'end', 'active', 'plan_hidden']
    list_filter = ['active']
    list_editable = ['active']
    ordering = ['-start']
    readonly_fields = ['status_url', 'plan_hidden', 'plan_published_at', 'toggle_plan_visibility']
    actions = ['publish', 'unpublish']

    def add_view(self, request, form_url='', extra_context=None):
        # Always use wizard to create new events (the built-in form wouldn't work anyways since the timezone cannot
        # be specified before starting to fill the form)
        return redirect("admin:new_event_wizard_start")

    def get_urls(self):
        urls = get_admin_urls_event_wizard(self.admin_site)
        urls.extend(get_admin_urls_event(self.admin_site))
        if apps.is_installed("AKScheduling"):
            from AKScheduling.urls import get_admin_urls_scheduling
            urls.extend(get_admin_urls_scheduling(self.admin_site))
        urls.extend([
            path('plan/publish/', PlanPublishView.as_view(), name="plan-publish"),
            path('plan/unpublish/', PlanUnpublishView.as_view(), name="plan-unpublish"),
            path('<slug:event_slug>/defaultSlots/', DefaultSlotEditorView.as_view(), name="default-slots-editor"),
            path('<slug:event_slug>/importRooms/', RoomBatchCreationView.as_view(), name="room-import"),
        ])
        urls.extend(super().get_urls())
        return urls

    @display(description=_("Status"))
    def status_url(self, obj):
        return format_html("<a href='{url}'>{text}</a>",
                           url=reverse_lazy('admin:event_status', kwargs={'slug': obj.slug}), text=_("Status"))

    @display(description=_("Toggle plan visibility"))
    def toggle_plan_visibility(self, obj):
        if obj.plan_hidden:
            url = f"{reverse_lazy('admin:plan-publish')}?pks={obj.pk}"
            text = _('Publish plan')
        else:
            url = f"{reverse_lazy('admin:plan-unpublish')}?pks={obj.pk}"
            text = _('Unpublish plan')
        return format_html("<a href='{url}'>{text}</a>", url=url, text=text)

    def get_form(self, request, obj=None, change=False, **kwargs):
        # Use timezone of event
        timezone.activate(obj.timezone)
        return super().get_form(request, obj, change, **kwargs)

    @action(description=_('Publish plan'))
    def publish(self, request, queryset):
        selected = queryset.values_list('pk', flat=True)
        return HttpResponseRedirect(f"{reverse_lazy('admin:plan-publish')}?pks={','.join(str(pk) for pk in selected)}")

    @action(description=_('Unpublish plan'))
    def unpublish(self, request, queryset):
        selected = queryset.values_list('pk', flat=True)
        return HttpResponseRedirect(f"{reverse_lazy('admin:plan-unpublish')}?pks={','.join(str(pk) for pk in selected)}")


@admin.register(AKOwner)
class AKOwnerAdmin(admin.ModelAdmin):
    model = AKOwner
    list_display = ['name', 'institution', 'event']
    list_filter = ['event', 'institution']
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
    list_display = ['name', 'short_name', 'category', 'track', 'is_wish', 'interest', 'interest_counter', 'event']
    list_filter = ['event', WishFilter, ('category', EventRelatedFieldListFilter), ('requirements', EventRelatedFieldListFilter)]
    list_editable = ['short_name', 'track', 'interest_counter']
    ordering = ['pk']
    actions = ['wiki_export', 'reset_interest', 'reset_interest_counter']
    form = AKAdminForm

    @display(boolean=True)
    def is_wish(self, obj):
        return obj.wish

    @action(description=_("Export to wiki syntax"))
    def wiki_export(self, request, queryset):
        # Only export when all AKs belong to the same event
        if queryset.values("event").distinct().count() == 1:
            event = queryset.first().event
            pks = set(ak.pk for ak in queryset.all())
            categories_with_aks = event.get_categories_with_aks(wishes_seperately=False, filter=lambda ak: ak.pk in pks,
                                                                hide_empty_categories=True)
            return render(request, 'admin/AKModel/wiki_export.html', context={"categories_with_aks": categories_with_aks})
        self.message_user(request, _("Cannot export AKs from more than one event at the same time."), messages.ERROR)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'event':
            kwargs['initial'] = Event.get_next_active()
        return super(AKAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

    def get_urls(self):
        urls = [
            path('reset-interest/', AKResetInterestView.as_view(), name="ak-reset-interest"),
            path('reset-interest-counter/', AKResetInterestCounterView.as_view(), name="ak-reset-interest-counter"),
        ]
        urls.extend(super().get_urls())
        return urls

    @action(description=_("Reset interest in AKs"))
    def reset_interest(self, request, queryset):
        selected = queryset.values_list('pk', flat=True)
        return HttpResponseRedirect(f"{reverse_lazy('admin:ak-reset-interest')}?pks={','.join(str(pk) for pk in selected)}")

    @action(description=_("Reset AKs' interest counters"))
    def reset_interest_counter(self, request, queryset):
        selected = queryset.values_list('pk', flat=True)
        return HttpResponseRedirect(f"{reverse_lazy('admin:ak-reset-interest-counter')}?pks={','.join(str(pk) for pk in selected)}")


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
    list_filter = ['event', ('properties', EventRelatedFieldListFilter), 'location']
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
    list_filter = ['event', ('room', EventRelatedFieldListFilter)]
    ordering = ['start']
    readonly_fields = ['ak_details_link', 'updated']
    form = AKSlotAdminForm

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

    @display(description=_('AK Details'))
    def ak_details_link(self, akslot):
        if apps.is_installed("AKSubmission") and akslot.ak is not None:
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
    list_display = ['type', 'level', 'get_details', 'manually_resolved']
    list_filter = ['event']
    readonly_fields = ['timestamp']
    form = ConstraintViolationAdminForm
    actions = ['mark_resolved', 'set_violation', 'set_warning']

    def get_urls(self):
        urls = [
            path('mark-resolved/', CVMarkResolvedView.as_view(), name="cv-mark-resolved"),
            path('set-violation/', CVSetLevelViolationView.as_view(), name="cv-set-violation"),
            path('set-warning/', CVSetLevelWarningView.as_view(), name="cv-set-warning"),
        ]
        urls.extend(super().get_urls())
        return urls

    @action(description=_("Mark Constraint Violations as manually resolved"))
    def mark_resolved(self, request, queryset):
        selected = queryset.values_list('pk', flat=True)
        return HttpResponseRedirect(f"{reverse_lazy('admin:cv-mark-resolved')}?pks={','.join(str(pk) for pk in selected)}")

    @action(description=_('Set Constraint Violations to level "violation"'))
    def set_violation(self, request, queryset):
        selected = queryset.values_list('pk', flat=True)
        return HttpResponseRedirect(f"{reverse_lazy('admin:cv-set-violation')}?pks={','.join(str(pk) for pk in selected)}")

    @action(description=_('Set Constraint Violations to level "warning"'))
    def set_warning(self, request, queryset):
        selected = queryset.values_list('pk', flat=True)
        return HttpResponseRedirect(f"{reverse_lazy('admin:cv-set-warning')}?pks={','.join(str(pk) for pk in selected)}")


class DefaultSlotAdminForm(forms.ModelForm):
    class Meta:
        widgets = {
            'primary_categories': forms.CheckboxSelectMultiple
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter possible values for foreign keys & m2m when event is specified
        if hasattr(self.instance, "event") and self.instance.event is not None:
            self.fields["primary_categories"].queryset = AKCategory.objects.filter(event=self.instance.event)


@admin.register(DefaultSlot)
class DefaultSlotAdmin(admin.ModelAdmin):
    list_display = ['start_simplified', 'end_simplified', 'event']
    list_filter = ['event']
    form = DefaultSlotAdminForm

    def get_form(self, request, obj=None, change=False, **kwargs):
        # Use timezone of event
        if obj is not None:
            timezone.activate(obj.event.timezone)
        return super().get_form(request, obj, change, **kwargs)
