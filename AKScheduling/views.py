from django.urls import reverse_lazy
from django.views.generic import ListView
from django.utils.translation import gettext_lazy as _

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
