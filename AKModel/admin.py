from django import forms
from django.apps import apps
from django.contrib import admin, messages
from django.contrib.admin import SimpleListFilter, RelatedFieldListFilter, action, display
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User # pylint: disable=E5142
from django.db.models import Count, F
from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect
from django.urls import reverse_lazy, path
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from simple_history.admin import SimpleHistoryAdmin

from AKModel.availability.models import Availability
from AKModel.forms import RoomFormWithAvailabilities
from AKModel.models import Event, AKOwner, AKCategory, AKTrack, AKRequirement, AK, AKSlot, Room, AKOrgaMessage, \
    ConstraintViolation, DefaultSlot, AKType
from AKModel.urls import get_admin_urls_event_wizard, get_admin_urls_event
from AKModel.views.ak import AKResetInterestView, AKResetInterestCounterView
from AKModel.views.manage import CVMarkResolvedView, CVSetLevelViolationView, CVSetLevelWarningView, ClearScheduleView


class EventRelatedFieldListFilter(RelatedFieldListFilter):
    """
    Reusable filter to restrict the possible choices of a field to those belonging to a certain event
    as specified in the event__id__exact GET parameter.
    The choices are only restricted if this parameter is present, otherwise all choices are used/returned
    """
    def field_choices(self, field, request, model_admin):
        ordering = self.field_admin_ordering(field, request, model_admin)
        limit_choices = {}
        if "event__id__exact" in request.GET:
            limit_choices['event__id__exact'] = request.GET["event__id__exact"]
        return field.get_choices(include_blank=False, limit_choices_to=limit_choices, ordering=ordering)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    """
    Admin interface for Event

    This allows to edit most fields of an event, some can only be changed by admin actions, since they have side effects

    This admin interface registers additional views as defined in urls.py, the wizard, and the full scheduling
    functionality if the AKScheduling app is active.

    The interface overrides the built-in creation interface for a new event and replaces it with the event creation
    wizard.
    """
    model = Event
    list_display = ['name', 'status_url', 'place', 'start', 'end', 'active', 'plan_hidden', 'poll_hidden']
    list_filter = ['active']
    list_editable = ['active']
    ordering = ['-start']
    readonly_fields = [
        'status_url',
        'plan_hidden', 'plan_published_at', 'toggle_plan_visibility',
        'poll_hidden', 'poll_published_at', 'toggle_poll_visibility',
    ]
    actions = ['publish_plan', 'unpublish_plan', 'publish_poll', 'unpublish_poll']

    def add_view(self, request, form_url='', extra_context=None):
        # Override
        # Always use wizard to create new events (the built-in form wouldn't work anyway since the timezone cannot
        # be specified before starting to fill the form)
        return redirect("admin:new_event_wizard_start")

    def get_urls(self):
        """
        Get all event-related URLs
        This will be both the built-in URLs and additional views providing additional functionality
        :return: list of all relevant URLs
        :rtype: List[path]
        """
        # Load wizard URLs and the additional URLs defined in urls.py
        # (first, to have the highest priority when overriding views)
        urls = get_admin_urls_event_wizard(self.admin_site)
        urls.extend(get_admin_urls_event(self.admin_site))

        # Make scheduling admin views available if app is active
        if apps.is_installed("AKScheduling"):
            from AKScheduling.urls import get_admin_urls_scheduling  # pylint: disable=import-outside-toplevel
            urls.extend(get_admin_urls_scheduling(self.admin_site))

        if apps.is_installed("AKSolverInterface"):
            from AKSolverInterface.urls import get_admin_urls_solver_interface  # pylint: disable=import-outside-toplevel
            urls.extend(get_admin_urls_solver_interface(self.admin_site))

        # Make sure built-in URLs are available as well
        urls.extend(super().get_urls())
        return urls

    @display(description=_("Status"))
    def status_url(self, obj):
        """
        Define a read-only field to go to the status page of the event

        :param obj: the event to link
        :return: status page link (HTML)
        :rtype: str
        """
        return format_html("<a href='{url}'>{text}</a>",
                           url=reverse_lazy('admin:event_status', kwargs={'event_slug': obj.slug}), text=_("Status"))

    @display(description=_("Toggle plan visibility"))
    def toggle_plan_visibility(self, obj):
        """
        Define a read-only field to toggle the visibility of the plan of this event
        This will choose from two different link targets/views depending on the current visibility status

        :param obj: event to change the visibility of the plan for
        :return: toggling link (HTML)
        :rtype: str
        """
        if obj.plan_hidden:
            url = f"{reverse_lazy('admin:plan-publish')}?pks={obj.pk}"
            text = _('Publish plan')
        else:
            url = f"{reverse_lazy('admin:plan-unpublish')}?pks={obj.pk}"
            text = _('Unpublish plan')
        return format_html("<a href='{url}'>{text}</a>", url=url, text=text)

    @display(description=_("Toggle poll visibility"))
    def toggle_poll_visibility(self, obj):
        """
        Define a read-only field to toggle the visibility of the preference poll of this event
        This will choose from two different link targets/views depending on the current visibility status

        :param obj: event to change the visibility of the poll for
        :return: toggling link (HTML)
        :rtype: str
        """
        if obj.poll_hidden:
            url = f"{reverse_lazy('admin:poll-publish')}?pks={obj.pk}"
            text = _('Publish preference poll')
        else:
            url = f"{reverse_lazy('admin:poll-unpublish')}?pks={obj.pk}"
            text = _('Unpublish preference poll')
        return format_html("<a href='{url}'>{text}</a>", url=url, text=text)

    def get_form(self, request, obj=None, change=False, **kwargs):
        # Override (update) form rendering to make sure the timezone of the event is used
        timezone.activate(obj.timezone)
        return super().get_form(request, obj, change, **kwargs)

    @action(description=_('Publish plan'))
    def publish_plan(self, request, queryset):
        """
        Admin action to publish the plan
        """
        selected = queryset.values_list('pk', flat=True)
        return HttpResponseRedirect(f"{reverse_lazy('admin:plan-publish')}?pks={','.join(str(pk) for pk in selected)}")

    @action(description=_('Unpublish plan'))
    def unpublish_plan(self, request, queryset):
        """
        Admin action to hide the plan
        """
        selected = queryset.values_list('pk', flat=True)
        return HttpResponseRedirect(
            f"{reverse_lazy('admin:plan-unpublish')}?pks={','.join(str(pk) for pk in selected)}")

    @action(description=_('Publish preference poll'))
    def publish_poll(self, request, queryset):
        """
        Admin action to publish the preference poll
        """
        selected = queryset.values_list('pk', flat=True)
        return HttpResponseRedirect(f"{reverse_lazy('admin:poll-publish')}?pks={','.join(str(pk) for pk in selected)}")

    @action(description=_('Unpublish preference poll'))
    def unpublish_poll(self, request, queryset):
        """
        Admin action to hide the preference poll
        """
        selected = queryset.values_list('pk', flat=True)
        return HttpResponseRedirect(
            f"{reverse_lazy('admin:poll-unpublish')}?pks={','.join(str(pk) for pk in selected)}")


class PrepopulateWithNextActiveEventMixin:
    """
    Mixin for automated pre-population of the event field
    """
    # pylint: disable=too-few-public-methods

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Override field generation for foreign key fields to introduce special handling for event fields:
        Pre-populate the event field with the next active event (since that is the most likeliest event to be worked
        on in the admin interface) to make creation of new owners easier
        """
        if db_field.name == 'event':
            kwargs['initial'] = Event.get_next_active()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(AKOwner)
class AKOwnerAdmin(PrepopulateWithNextActiveEventMixin, admin.ModelAdmin):
    """
    Admin interface for AKOwner
    """
    model = AKOwner
    list_display = ['name', 'institution', 'event', 'aks_url']
    list_filter = ['event', 'institution']
    list_editable = []
    ordering = ['name']
    readonly_fields = ['aks_url']

    @display(description=_("AKs"))
    def aks_url(self, obj):
        """
        Define a read-only field to go to the list of all AKs by this user

        :param obj: user
        :return: AK list page link (HTML)
        :rtype: str
        """
        return format_html("<a href='{url}'>{text}</a>",
                           url=reverse_lazy('admin:aks_by_owner', kwargs={'event_slug': obj.event.slug, 'pk': obj.pk}),
                           text=obj.ak_set.count())


@admin.register(AKCategory)
class AKCategoryAdmin(PrepopulateWithNextActiveEventMixin, admin.ModelAdmin):
    """
    Admin interface for AKCategory
    """
    model = AKCategory
    list_display = ['name', 'color', 'event']
    list_filter = ['event']
    list_editable = ['color']
    ordering = ['name']


@admin.register(AKTrack)
class AKTrackAdmin(PrepopulateWithNextActiveEventMixin, admin.ModelAdmin):
    """
    Admin interface for AKTrack
    """
    model = AKTrack
    list_display = ['name', 'color', 'event']
    list_filter = ['event']
    list_editable = ['color']
    ordering = ['name']


@admin.register(AKRequirement)
class AKRequirementAdmin(PrepopulateWithNextActiveEventMixin, admin.ModelAdmin):
    """
    Admin interface for AKRequirements
    """
    model = AKRequirement
    list_display = ['name', 'event']
    list_filter = ['event']
    list_editable = []
    ordering = ['name']


@admin.register(AKType)
class AKTypeAdmin(PrepopulateWithNextActiveEventMixin, admin.ModelAdmin):
    """
    Admin interface for AKRequirements
    """
    model = AKType
    list_display = ['name', 'event']
    list_filter = ['event']
    list_editable = []
    ordering = ['name']


class WishFilter(SimpleListFilter):
    """
    Re-usable filter for wishes
    """
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
    """
    Modified admin form for AKs, to be used in :class:`AKAdmin`
    """
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
            self.fields["types"].queryset = AKType.objects.filter(event=self.instance.event)


@admin.register(AK)
class AKAdmin(PrepopulateWithNextActiveEventMixin, SimpleHistoryAdmin):
    """
    Admin interface for AKs

    Uses a modified form (see :class:`AKAdminForm`)
    """
    model = AK
    list_display = ['name', 'short_name', 'category', 'track', 'is_wish', 'interest', 'interest_counter', 'event']
    list_filter = ['event',
                   WishFilter,
                   ('category', EventRelatedFieldListFilter),
                   ('requirements', EventRelatedFieldListFilter),
                   ('types', EventRelatedFieldListFilter),
                   ]
    list_editable = ['short_name', 'track', 'interest_counter']
    ordering = ['pk']
    actions = ['wiki_export', 'reset_interest', 'reset_interest_counter']
    form = AKAdminForm

    @display(boolean=True)
    def is_wish(self, obj):
        """
        Property: Is this AK a wish?
        """
        return obj.wish

    @action(description=_("Export to wiki syntax"))
    def wiki_export(self, request, queryset):
        """
        Action: Export to wiki syntax
        This will use the wiki export view (therefore, all AKs have to have the same event to correclty handle the
        categories and to prevent accidentially merging AKs from different events in the wiki)
        but restrict the AKs to the ones explicitly selected here.
        """
        # Only export when all AKs belong to the same event
        if queryset.values("event").distinct().count() == 1:
            event = queryset.first().event
            pks = set(ak.pk for ak in queryset.all())
            categories_with_aks = event.get_categories_with_aks(wishes_seperately=False,
                                                                filter_func=lambda ak: ak.pk in pks,
                                                                hide_empty_categories=True)
            return render(request, 'admin/AKModel/wiki_export.html',
                          context={"categories_with_aks": categories_with_aks})
        self.message_user(request, _("Cannot export AKs from more than one event at the same time."), messages.ERROR)
        return redirect('admin:AKModel_ak_changelist')

    def get_urls(self):
        """
        Add additional URLs/views
        Currently used to reset the interest field and interest counter field
        """
        urls = [
            path('reset-interest/', AKResetInterestView.as_view(), name="ak-reset-interest"),
            path('reset-interest-counter/', AKResetInterestCounterView.as_view(), name="ak-reset-interest-counter"),
        ]
        urls.extend(super().get_urls())
        return urls

    @action(description=_("Reset interest in AKs"))
    def reset_interest(self, request, queryset):
        """
        Action: Reset interest field for the given AKs
        Will use a typical admin confirmation view flow
        """
        selected = queryset.values_list('pk', flat=True)
        return HttpResponseRedirect(
            f"{reverse_lazy('admin:ak-reset-interest')}?pks={','.join(str(pk) for pk in selected)}")

    @action(description=_("Reset AKs' interest counters"))
    def reset_interest_counter(self, request, queryset):
        """
        Action: Reset interest counter field for the given AKs
        Will use a typical admin confirmation view flow
        """
        selected = queryset.values_list('pk', flat=True)
        return HttpResponseRedirect(
            f"{reverse_lazy('admin:ak-reset-interest-counter')}?pks={','.join(str(pk) for pk in selected)}")


@admin.register(Room)
class RoomAdmin(PrepopulateWithNextActiveEventMixin, admin.ModelAdmin):
    """
    Admin interface for Rooms
    """
    model = Room
    list_display = ['name', 'location', 'capacity', 'event']
    list_filter = ['event', ('properties', EventRelatedFieldListFilter), 'location']
    list_editable = []
    ordering = ['location', 'name']
    change_form_template = "admin/AKModel/room_change_form.html"

    def add_view(self, request, form_url='', extra_context=None):
        # Override creation view
        # Use custom view for room creation (either room form or combined form if virtual rooms are supported)
        return redirect("admin:room-new")

    def get_form(self, request, obj=None, change=False, **kwargs):
        # Override form creation to use a form that allows to specify availabilites of the room once this room is
        # associated with an event (so not before the first saving) since the timezone information and event start
        # and end are needed to correclty render the calendar
        if obj is not None:
            return RoomFormWithAvailabilities
        return super().get_form(request, obj, change, **kwargs)

    def get_urls(self):
        """
        Add additional URLs/views
        This is currently used to adapt the creation form behavior, to allow the creation of virtual rooms in-place
        when the support for virtual rooms is turned on (AKOnline app active)
        """
        # pylint: disable=import-outside-toplevel
        if apps.is_installed("AKOnline"):
            from AKOnline.views import RoomCreationWithVirtualView as RoomCreationView
        else:
            from .views.room import RoomCreationView

        urls = [
            path('new/', self.admin_site.admin_view(RoomCreationView.as_view()), name="room-new"),
        ]
        urls.extend(super().get_urls())
        return urls


class EventTimezoneFormMixin:
    """
    Mixin to enforce the usage of the timezone of the associated event in forms
    """
    # pylint: disable=too-few-public-methods

    def get_form(self, request, obj=None, change=False, **kwargs):
        """
        Override form creation, use timezone of associated event
        """
        if obj is not None and obj.event.timezone:
            timezone.activate(obj.event.timezone)
        # No timezone available? Use UTC
        else:
            timezone.activate("UTC")
        return super().get_form(request, obj, change, **kwargs)


class AKSlotAdminForm(forms.ModelForm):
    """
    Modified admin form for AKSlots, to be used in :class:`AKSlotAdmin`
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter possible values for foreign keys when event is specified
        if hasattr(self.instance, "event") and self.instance.event is not None:
            self.fields["ak"].queryset = AK.objects.filter(event=self.instance.event)
            self.fields["room"].queryset = Room.objects.filter(event=self.instance.event)


@admin.register(AKSlot)
class AKSlotAdmin(EventTimezoneFormMixin, PrepopulateWithNextActiveEventMixin, admin.ModelAdmin):
    """
    Admin interface for AKSlots

    Uses a modified form (see :class:`AKSlotAdminForm`)
    """
    model = AKSlot
    list_display = ['id', 'ak', 'room', 'start', 'duration', 'event']
    list_filter = ['event', "fixed", ('room', EventRelatedFieldListFilter)]
    ordering = ['start']
    readonly_fields = ['ak_details_link', 'updated']
    form = AKSlotAdminForm
    actions = ["reset_scheduling"]

    @display(description=_('AK Details'))
    def ak_details_link(self, akslot):
        """
        Define a read-only field to link the details of the associated AK

        :param obj: the AK to link
        :return: AK detail page page link (HTML)
        :rtype: str
        """
        if apps.is_installed("AKSubmission") and akslot.ak is not None:
            link = f"<a href='{ akslot.ak.detail_url }'>{str(akslot.ak)}</a>"
            return mark_safe(str(link))
        return "-"

    def get_urls(self):
        """
        Add additional URLs/views
        """
        urls = [
            path('clear-schedule/', ClearScheduleView.as_view(), name="clear-schedule"),
        ]
        urls.extend(super().get_urls())
        return urls

    @action(description=_("Clear start/rooms"))
    def reset_scheduling(self, request, queryset):
        """
        Action: Reset start and room field for the given AKs
        Will use a typical admin confirmation view flow
        """
        if queryset.filter(fixed=True).exists():
            self.message_user(
                request,
                _(
                        "Cannot reset scheduling for fixed AKs. "
                        "Please make sure to filter out fixed AKs first."
                ),
                messages.ERROR,
            )
            return redirect('admin:AKModel_akslot_changelist')
        selected = queryset.values_list('pk', flat=True)
        return HttpResponseRedirect(
            f"{reverse_lazy('admin:clear-schedule')}?pks={','.join(str(pk) for pk in selected)}")

    ak_details_link.short_description = _('AK Details')


@admin.register(Availability)
class AvailabilityAdmin(EventTimezoneFormMixin, admin.ModelAdmin):
    """
    Admin interface for Availabilities
    """
    list_display = ['__str__', 'event']
    list_filter = ['event']


@admin.register(AKOrgaMessage)
class AKOrgaMessageAdmin(admin.ModelAdmin):
    """
    Admin interface for AKOrgaMessages
    """
    list_display = ['timestamp', 'ak', 'text', 'resolved']
    list_filter = ['ak__event']
    readonly_fields = ['timestamp', 'ak', 'text']


class ConstraintViolationAdminForm(forms.ModelForm):
    """
    Adapted admin form for constraint violations for usage in :class:`ConstraintViolationAdmin`)
    """
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
    """
    Admin interface for constraint violations
    Uses an adapted form (see :class:`ConstraintViolationAdminForm`)
    """
    list_display = ['type', 'level', 'get_details', 'manually_resolved']
    list_filter = ['event']
    readonly_fields = ['timestamp']
    form = ConstraintViolationAdminForm
    actions = ['mark_resolved', 'set_violation', 'set_warning']

    def get_urls(self):
        """
        Add additional URLs/views to change status and severity of CVs
        """
        urls = [
            path('mark-resolved/', CVMarkResolvedView.as_view(), name="cv-mark-resolved"),
            path('set-violation/', CVSetLevelViolationView.as_view(), name="cv-set-violation"),
            path('set-warning/', CVSetLevelWarningView.as_view(), name="cv-set-warning"),
        ]
        urls.extend(super().get_urls())
        return urls

    @action(description=_("Mark Constraint Violations as manually resolved"))
    def mark_resolved(self, request, queryset):
        """
        Action: Mark CV as resolved
        """
        selected = queryset.values_list('pk', flat=True)
        return HttpResponseRedirect(
            f"{reverse_lazy('admin:cv-mark-resolved')}?pks={','.join(str(pk) for pk in selected)}")

    @action(description=_('Set Constraint Violations to level "violation"'))
    def set_violation(self, request, queryset):
        """
        Action: Promote CV to level violation
        """
        selected = queryset.values_list('pk', flat=True)
        return HttpResponseRedirect(
            f"{reverse_lazy('admin:cv-set-violation')}?pks={','.join(str(pk) for pk in selected)}")

    @action(description=_('Set Constraint Violations to level "warning"'))
    def set_warning(self, request, queryset):
        """
        Action: Set CV to level warning
        """
        selected = queryset.values_list('pk', flat=True)
        return HttpResponseRedirect(
            f"{reverse_lazy('admin:cv-set-warning')}?pks={','.join(str(pk) for pk in selected)}")


class DefaultSlotAdminForm(forms.ModelForm):
    """
    Adapted admin form for DefaultSlot for usage in :class:`DefaultSlotAdmin`
    """
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
class DefaultSlotAdmin(EventTimezoneFormMixin, admin.ModelAdmin):
    """
    Admin interface for default slots
    Uses an adapted form (see :class:`DefaultSlotAdminForm`)
    """
    list_display = ['start_simplified', 'end_simplified', 'event']
    list_filter = ['event']
    form = DefaultSlotAdminForm


# Define a new User admin
class UserAdmin(BaseUserAdmin):
    """
    Admin interface for Users
    Enhances the built-in UserAdmin with additional actions to activate and deactivate users and a custom selection
    of displayed properties in overview list
    """
    list_display = ["username", "email", "is_active", "is_staff", "is_superuser"]
    actions = ['activate', 'deactivate']

    @admin.action(description=_("Activate selected users"))
    def activate(self, request, queryset):
        """
        Bulk activate users

        :param request: HTTP request
        :param queryset: queryset containing all users that should be activated
        """
        queryset.update(is_active=True)
        self.message_user(request, _("The selected users have been activated."))

    @admin.action(description=_("Deactivate selected users"))
    def deactivate(self, request, queryset):
        """
        Bulk deactivate users

        :param request: HTTP request
        :param queryset: queryset containing all users that should be deactivated
        """
        queryset.update(is_active=False)
        self.message_user(request, _("The selected users have been deactivated."))


# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
