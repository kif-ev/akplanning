from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, DetailView

from AKModel.models import AKSlot, AKTrack, Event, AK
from AKModel.views import AdminViewMixin, FilterByEventSlugMixin


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
            if ak.wish and ak.akslot_set.count() > 0:
                ak_wishes_with_slots.append(ak)
            if not ak.wish and ak.akslot_set.count() == 0:
                aks_without_slots.append(ak)
            if ak.notes != "":
                aks_with_comment.append(ak)
            if ak.availabilities.count() == 0:
                aks_without_availabilities.append(ak)

        context["aks_with_comment"] = aks_with_comment
        context["ak_wishes_with_slots"] = ak_wishes_with_slots
        context["aks_without_slots"] = aks_without_slots
        context["aks_without_availabilities"] = aks_without_availabilities

        return context
