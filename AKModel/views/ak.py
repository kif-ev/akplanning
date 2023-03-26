from django.contrib import messages
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, DetailView

from AKModel.metaviews.admin import AdminViewMixin, FilterByEventSlugMixin, EventSlugMixin, IntermediateAdminView, \
    IntermediateAdminActionView
from AKModel.models import AKRequirement, AKSlot, Event, AKOrgaMessage, AK


class AKRequirementOverview(AdminViewMixin, FilterByEventSlugMixin, ListView):
    model = AKRequirement
    context_object_name = "requirements"
    title = _("Requirements for Event")
    template_name = "admin/AKModel/requirements_overview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["event"] = self.event
        context["site_url"] = reverse_lazy("dashboard:dashboard_event", kwargs={'slug': context["event"].slug})
        return context


class AKCSVExportView(AdminViewMixin, FilterByEventSlugMixin, ListView):
    template_name = "admin/AKModel/ak_csv_export.html"
    model = AKSlot
    context_object_name = "slots"
    title = _("AK CSV Export")

    def get_queryset(self):
        return super().get_queryset().order_by("ak__track")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context


class AKWikiExportView(AdminViewMixin, DetailView):
    template_name = "admin/AKModel/wiki_export.html"
    model = Event
    context_object_name = "event"
    title = _("AK Wiki Export")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        categories_with_aks, ak_wishes = context["event"].get_categories_with_aks(
            wishes_seperately=True,
            filter=lambda ak: ak.include_in_export
        )

        context["categories_with_aks"] = [(category.name, ak_list) for category, ak_list in categories_with_aks]
        context["categories_with_aks"].append((_("Wishes"), ak_wishes))

        return context


class AKMessageDeleteView(EventSlugMixin, IntermediateAdminView):
    template_name = "admin/AKModel/message_delete.html"
    title = _("Delete AK Orga Messages")

    def get_orga_messages_for_event(self, event):
        return AKOrgaMessage.objects.filter(ak__event=event)

    def get_success_url(self):
        return reverse_lazy('admin:event_status', kwargs={'slug': self.event.slug})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["ak_messages"] = self.get_orga_messages_for_event(self.event)
        return context

    def form_valid(self, form):
        self.get_orga_messages_for_event(self.event).delete()
        messages.add_message(self.request, messages.SUCCESS, _("AK Orga Messages successfully deleted"))
        return super().form_valid(form)


class AKResetInterestView(IntermediateAdminActionView):
    title = _("Reset interest in AKs")
    model = AK
    confirmation_message = _("Interest of the following AKs will be set to not filled (-1):")
    success_message = _("Reset of interest in AKs successful.")

    def action(self, form):
        self.entities.update(interest=-1)


class AKResetInterestCounterView(IntermediateAdminActionView):
    title = _("Reset AKs' interest counters")
    model = AK
    confirmation_message = _("Interest counter of the following AKs will be set to 0:")
    success_message = _("AKs' interest counters set back to 0.")

    def action(self, form):
        self.entities.update(interest_counter=0)
