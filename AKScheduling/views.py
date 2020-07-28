from django.views.generic import ListView
from django.utils.translation import gettext_lazy as _

from AKModel.availability.models import Availability
from AKModel.models import AKSlot
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
    context_object_name = "akslots"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context["title"] = f"{_('Scheduling')} for {context['event']}"

        context["event"] = self.event
        context["start"] = self.event.start
        context["end"] = self.event.end

        context["rooms"] = self.event.room_set.all()

        context["availabilities"] = Availability.objects.filter(event=self.event, room__isnull=False)

        return context
