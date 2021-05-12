from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, DetailView

from AKModel.models import AKSlot, AKTrack, Event
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
