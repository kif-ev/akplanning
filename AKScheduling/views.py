from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, DetailView, UpdateView

from AKModel.metaviews import status_manager
from AKModel.metaviews.status import TemplateStatusWidget
from AKModel.models import AKSlot, AKTrack, Event, AK, AKCategory
from AKModel.metaviews.admin import EventSlugMixin, FilterByEventSlugMixin, AdminViewMixin, IntermediateAdminView
from AKScheduling.forms import AKInterestForm, AKAddSlotForm


class UnscheduledSlotsAdminView(AdminViewMixin, FilterByEventSlugMixin, ListView):
    """
    Admin view: Get a list of all unscheduled slots
    """
    template_name = "admin/AKScheduling/unscheduled.html"
    model = AKSlot
    context_object_name = "akslots"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"{_('Unscheduled AK Slots')} for {context['event']}"
        return context

    def get_queryset(self):
        return super().get_queryset().filter(start=None)


class SchedulingAdminView(AdminViewMixin, FilterByEventSlugMixin, ListView):
    """
    Admin view: Scheduler

    View and adapt the schedule of an event. This view heavily uses JavaScript to display a calendar view plus
    a list of unscheduled slots and to allow dragging slots in and into the calendar
    """
    template_name = "admin/AKScheduling/scheduling.html"
    model = AKSlot
    context_object_name = "slots_unscheduled"

    def get_queryset(self):
        return super().get_queryset().filter(start__isnull=True).select_related('event', 'ak', 'ak__track', 'ak__category').prefetch_related('ak__types', 'ak__owners', 'ak__conflicts', 'ak__prerequisites', 'ak__requirements').order_by('ak__track', 'ak')

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context["title"] = f"{_('Scheduling')} for {context['event']}"

        context["event"] = self.event
        context["start"] = self.event.start
        context["end"] = self.event.end

        context["akSlotAddForm"] = AKAddSlotForm(self.event)

        return context


class TrackAdminView(AdminViewMixin, FilterByEventSlugMixin, ListView):
    """
    Admin view: Distribute AKs to tracks

    Again using JavaScript, the user can here see a list of all AKs split-up by tracks and can move them to other or
    even new tracks using drag and drop. The state is then automatically synchronized via API calls in the background
    """
    template_name = "admin/AKScheduling/manage_tracks.html"
    model = AKTrack
    context_object_name = "tracks"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context["aks_without_track"] = self.event.ak_set.select_related('category').filter(track=None)
        return context


class ConstraintViolationsAdminView(AdminViewMixin, DetailView):
    """
    Admin view: Inspect and adjust all constraint violations of the event

    This view populates a table of constraint violations via background API call (JavaScript), offers the option to
    see details or edit each of them and provides an auto-reload feature.
    """
    template_name = "admin/AKScheduling/constraint_violations.html"
    model = Event
    context_object_name = "event"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"{_('Constraint violations for')} {context['event']}"
        return context


class SpecialAttentionAKsAdminView(AdminViewMixin, DetailView):
    """
    Admin view: List all AKs that require special attention via scheduling, e.g., because of free-form comments,
    since there are slots even though it is a wish, or no slots even though it is an AK etc.
    """
    template_name = "admin/AKScheduling/special_attention.html"
    model = Event
    context_object_name = "event"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"{_('AKs requiring special attention for')} {context['event']}"

        # Load all "special" AKs from the database using annotations to reduce the amount of necessary queries
        aks = (AK.objects.filter(event=context["event"]).annotate(Count('owners', distinct=True))
               .annotate(Count('akslot', distinct=True)).annotate(Count('availabilities', distinct=True)))
        aks_with_comment = []
        ak_wishes_with_slots = []
        aks_without_availabilities = []
        aks_without_slots = []

        # Loop over all AKs of this event and identify all relevant factors that make the AK "special" and add them to
        # the respective lists if the AK fullfills an condition
        for ak in aks:
            if ak.notes != "":
                aks_with_comment.append(ak)

            if ak.owners__count == 0:
                if ak.akslot__count > 0:
                    ak_wishes_with_slots.append(ak)
            else:
                if ak.akslot__count == 0:
                    aks_without_slots.append(ak)
                if ak.availabilities__count == 0:
                    aks_without_availabilities.append(ak)

        context["aks_with_comment"] = aks_with_comment
        context["ak_wishes_with_slots"] = ak_wishes_with_slots
        context["aks_without_slots"] = aks_without_slots
        context["aks_without_availabilities"] = aks_without_availabilities

        return context


class InterestEnteringAdminView(SuccessMessageMixin, AdminViewMixin, EventSlugMixin, UpdateView):
    """
    Admin view: Form view to quickly store information about the interest in an AK
    (e.g., during presentation of the AK list)

    The view offers a field to update interest and manually set a comment for the current AK, but also features links
    to the AKs before and probably coming up next, as well as links to other AKs sorted by category, for quick
    and hazzle-free navigation during the AK presentation
    """
    template_name = "admin/AKScheduling/interest.html"
    model = AK
    context_object_name = "ak"
    form_class = AKInterestForm
    success_message = _("Interest updated")

    def get_success_url(self):
        return self.request.path

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"{_('Enter interest')}"

        # Sort AKs into different lists (by their category)
        ak_wishes = []
        categories_with_aks = []

        context["previous_ak"] = None
        context["next_ak"] = None
        last_ak = None
        next_is_next = False

        # Building the right navigation is a bit tricky since wishes have to be treated as an own category here
        # Hence, depending on the AK we are currently at (displaying the form for) we need to either:
        # Find other AK wishes (regardless of the category)...
        if context['ak'].wish:
            other_aks = [ak for ak in context['event'].ak_set.prefetch_related('owners').all() if ak.wish]
        # or other AKs of this category
        else:
            other_aks = [ak for ak in context['ak'].category.ak_set.prefetch_related('owners').all() if not ak.wish]

        # Use that list of other AKs belonging to this category to identify the previous and next AK (if any)
        for other_ak in other_aks:
            if next_is_next:
                context['next_ak'] = other_ak
                next_is_next = False
            elif other_ak.pk == context['ak'].pk :
                context['previous_ak'] = last_ak
                next_is_next = True
            last_ak = other_ak

        # Gather information for link lists for all categories (and wishes)
        for category in context['event'].akcategory_set.prefetch_related('ak_set').all():
            aks_for_category = []
            for ak in category.ak_set.prefetch_related('owners').all():
                if ak.wish:
                    ak_wishes.append(ak)
                else:
                    aks_for_category.append(ak)
            categories_with_aks.append((category, aks_for_category))

        # Make sure wishes have the right order (since the list was filled category by category before, this requires
        # explicitly reordering them by their primary key)
        ak_wishes.sort(key=lambda x: x.pk)
        categories_with_aks.append(
                (AKCategory(name=_("Wishes"), pk=0, description="-"), ak_wishes))

        context["categories_with_aks"] = categories_with_aks

        return context


class WishSlotCleanupView(EventSlugMixin, IntermediateAdminView):
    """
    Admin action view: Allow to delete all unscheduled slots for wishes

    The view will render a preview of all slots that are affected by this. It is not possible to manually choose
    which slots should be deleted (either all or none) and the functionality will therefore delete slots that were
    created in the time between rendering of the preview and running the action ofter confirmation as well.

    Due to the automated slot cleanup functionality for wishes in the AKSubmission app, this functionality should be
    rarely needed/used
    """
    title = _('Cleanup: Delete unscheduled slots for wishes')

    def get_success_url(self):
        return reverse_lazy('admin:special-attention', kwargs={'slug': self.event.slug})

    def get_preview(self):
        slots = self.event.get_unscheduled_wish_slots()
        return _("The following {count} unscheduled slots of wishes will be deleted:\n\n {slots}").format(
            count=len(slots),
            slots=", ".join(str(s.ak) for s in slots)
        )

    def form_valid(self, form):
        self.event.get_unscheduled_wish_slots().delete()
        messages.add_message(self.request, messages.SUCCESS, _("Unscheduled slots for wishes successfully deleted"))
        return super().form_valid(form)


class AvailabilityAutocreateView(EventSlugMixin, IntermediateAdminView):
    """
    Admin action view: Allow to automatically create default availabilities (event start to end) for all AKs without
    any manually specified availability information

    The view will render a preview of all AKs that are affected by this. It is not possible to manually choose
    which AKs should be affected (either all or none) and the functionality will therefore create availability entries
    for AKs that were created in the time between rendering of the preview and running the action ofter confirmation
    as well.
    """
    title = _('Create default availabilities for AKs')

    def get_success_url(self):
        return reverse_lazy('admin:special-attention', kwargs={'slug': self.event.slug})

    def get_preview(self):
        aks = self.event.get_aks_without_availabilities()
        return _("The following {count} AKs don't have any availability information. "
                 "Create default availability for them:\n\n {aks}").format(
            count=len(aks),
            aks=", ".join(str(ak) for ak in aks)
        )

    def form_valid(self, form):
        # Local import to prevent cyclic imports
        # pylint: disable=import-outside-toplevel
        from AKModel.availability.models import Availability

        success_count = 0
        for ak in self.event.get_aks_without_availabilities():
            try:
                availability = Availability.with_event_length(event=self.event, ak=ak)
                availability.save()
                success_count += 1
            except: # pylint: disable=bare-except
                messages.add_message(
                    self.request, messages.WARNING,
                    _("Could not create default availabilities for AK: {ak}").format(ak=ak)
                )

        messages.add_message(
            self.request, messages.SUCCESS,
            _("Created default availabilities for {count} AKs").format(count=success_count)
        )
        return super().form_valid(form)


@status_manager.register(name="scheduling_constraint_violations")
class CVWidget(TemplateStatusWidget):
    """
    Status page widget: Constraint violations
    """
    required_context_type = "event"
    title = _("Constraint Violations")
    template_name = "admin/AKScheduling/status/cvs.html"

    def render_status(self, context: {}) -> str:
        return "success" if context["constraint_violations_count"] == 0 else "warning"

    def get_context_data(self, context) -> dict:
        context = super().get_context_data(context)
        context["constraint_violations_count"] = (context["event"].constraintviolation_set
                                                  .filter(manually_resolved=False).count())
        return context
