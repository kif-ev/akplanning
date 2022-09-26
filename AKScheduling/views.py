from django.contrib.messages.views import SuccessMessageMixin
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, DetailView, UpdateView

from AKModel.models import AKSlot, AKTrack, Event, AK, AKCategory
from AKModel.views import AdminViewMixin, FilterByEventSlugMixin, EventSlugMixin
from AKScheduling.forms import AKInterestForm


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
        return super().get_queryset().filter(start__isnull=True).order_by('ak__track')

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context["title"] = f"{_('Scheduling')} for {context['event']}"

        context["event"] = self.event
        context["start"] = self.event.start
        context["end"] = self.event.end

        return context


class TrackAdminView(AdminViewMixin, FilterByEventSlugMixin, ListView):
    template_name = "admin/AKScheduling/manage_tracks.html"
    model = AKTrack
    context_object_name = "tracks"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context["aks_without_track"] = self.event.ak_set.filter(track=None)
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

        aks = AK.objects.filter(event=context["event"])
        aks_with_comment = []
        ak_wishes_with_slots = []
        aks_without_availabilities = []
        aks_without_slots = []

        for ak in aks:
            if ak.notes != "":
                aks_with_comment.append(ak)

            if ak.wish:
                if ak.akslot_set.count() > 0:
                    ak_wishes_with_slots.append(ak)
            else:
                if ak.akslot_set.count() == 0:
                    aks_without_slots.append(ak)
                if ak.availabilities.count() == 0:
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
            other_aks = [ak for ak in context['event'].ak_set.all() if ak.wish]
        # or other AKs of this category
        else:
            other_aks = [ak for ak in context['ak'].category.ak_set.all() if not ak.wish]

        for other_ak in other_aks:
            if next_is_next:
                context['next_ak'] = other_ak
                next_is_next = False
            elif other_ak.pk == context['ak'].pk :
                context['previous_ak'] = last_ak
                next_is_next = True
            last_ak = other_ak

        for category in context['event'].akcategory_set.all():
            aks_for_category = []
            for ak in category.ak_set.all():
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
