from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, DetailView, UpdateView

from AKModel.models import AKSlot, AKTrack, Event, AK, AKCategory
from AKModel.metaviews.admin import EventSlugMixin, FilterByEventSlugMixin, AdminViewMixin, IntermediateAdminView
from AKScheduling.forms import AKInterestForm
from AKSubmission.forms import AKAddSlotForm


class UnscheduledSlotsAdminView(AdminViewMixin, FilterByEventSlugMixin, ListView):
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
    template_name = "admin/AKScheduling/scheduling.html"
    model = AKSlot
    context_object_name = "slots_unscheduled"

    def get_queryset(self):
        return super().get_queryset().filter(start__isnull=True).select_related('event', 'ak').order_by('ak__track')

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context["title"] = f"{_('Scheduling')} for {context['event']}"

        context["event"] = self.event
        context["start"] = self.event.start
        context["end"] = self.event.end

        context["akSlotAddForm"] = AKAddSlotForm(self.event)

        return context


class TrackAdminView(AdminViewMixin, FilterByEventSlugMixin, ListView):
    template_name = "admin/AKScheduling/manage_tracks.html"
    model = AKTrack
    context_object_name = "tracks"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context["aks_without_track"] = self.event.ak_set.select_related('category').filter(track=None)
        return context


class ConstraintViolationsAdminView(AdminViewMixin, DetailView):
    template_name = "admin/AKScheduling/constraint_violations.html"
    model = Event
    context_object_name = "event"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"{_('Constraint violations for')} {context['event']}"
        return context


class SpecialAttentionAKsAdminView(AdminViewMixin, DetailView):
    template_name = "admin/AKScheduling/special_attention.html"
    model = Event
    context_object_name = "event"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"{_('AKs requiring special attention for')} {context['event']}"

        aks = AK.objects.filter(event=context["event"]).annotate(Count('owners', distinct=True)).annotate(Count('akslot', distinct=True)).annotate(Count('availabilities', distinct=True))
        aks_with_comment = []
        ak_wishes_with_slots = []
        aks_without_availabilities = []
        aks_without_slots = []

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

        # Find other AK wishes (regardless of the category)...
        if context['ak'].wish:
            other_aks = [ak for ak in context['event'].ak_set.prefetch_related('owners').all() if ak.wish]
        # or other AKs of this category
        else:
            other_aks = [ak for ak in context['ak'].category.ak_set.prefetch_related('owners').all() if not ak.wish]

        for other_ak in other_aks:
            if next_is_next:
                context['next_ak'] = other_ak
                next_is_next = False
            elif other_ak.pk == context['ak'].pk :
                context['previous_ak'] = last_ak
                next_is_next = True
            last_ak = other_ak

        for category in context['event'].akcategory_set.prefetch_related('ak_set').all():
            aks_for_category = []
            for ak in category.ak_set.prefetch_related('owners').all():
                if ak.wish:
                    ak_wishes.append(ak)
                else:
                    aks_for_category.append(ak)
            categories_with_aks.append((category, aks_for_category))

        ak_wishes.sort(key=lambda x: x.pk)
        categories_with_aks.append(
                (AKCategory(name=_("Wishes"), pk=0, description="-"), ak_wishes))

        context["categories_with_aks"] = categories_with_aks

        return context


class WishSlotCleanupView(EventSlugMixin, IntermediateAdminView):
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
        from AKModel.availability.models import Availability

        success_count = 0
        for ak in self.event.get_aks_without_availabilities():
            try:
                availability = Availability.with_event_length(event=self.event, ak=ak)
                availability.save()
                success_count += 1
            except:
                messages.add_message(
                    self.request, messages.WARNING,
                    _("Could not create default availabilities for AK: {ak}").format(ak=ak)
                )

        messages.add_message(
            self.request, messages.SUCCESS,
            _("Created default availabilities for {count} AKs").format(count=success_count)
        )
        return super().form_valid(form)
