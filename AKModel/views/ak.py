from django.contrib import messages
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, DetailView

from AKModel.forms import TrackAssignmentForm
from AKModel.metaviews.admin import AdminViewMixin, FilterByEventSlugMixin, EventSlugMixin, IntermediateAdminView, \
    IntermediateAdminActionView
from AKModel.models import AKRequirement, AKSlot, Event, AKOrgaMessage, AK, AKTrack


class AKRequirementOverview(AdminViewMixin, FilterByEventSlugMixin, ListView):
    """
    View: Display requirements for the given event
    """
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
    """
    View: Export all AK slots of this event in CSV format ordered by tracks
    Can, e.g., be used to produce printouts for manual paper scheduling
    """
    template_name = "admin/AKModel/ak_csv_export.html"
    model = AKSlot
    context_object_name = "slots"
    title = _("AK CSV Export")

    def get_queryset(self):
        return super().get_queryset().order_by("ak__track")


class SlotCSVExportView(AdminViewMixin, FilterByEventSlugMixin, ListView):
    """
    View: Export all AK slots of this event in CSV format ordered by their start time
    """
    template_name = "admin/AKModel/slots_csv_export.html"
    model = AKSlot
    context_object_name = "slots"
    title = _("Slot CSV Export")

    def get_queryset(self):
        return super().get_queryset().filter(start__isnull=False).order_by("start", "duration")


class AKWikiExportView(AdminViewMixin, DetailView):
    """
    View: Export AKs of this event in wiki syntax
    This will show one text field per category, with a separate category/field for wishes
    """
    template_name = "admin/AKModel/wiki_export.html"
    model = Event
    context_object_name = "event"
    title = _("AK Wiki Export")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        categories_with_aks, ak_wishes = context["event"].get_categories_with_aks(
            wishes_seperately=True,
            filter_func=lambda ak: ak.include_in_export
        )

        context["categories_with_aks"] = [(category.name, ak_list) for category, ak_list in categories_with_aks]
        context["categories_with_aks"].append((_("Wishes"), ak_wishes))

        return context


class AKMessageDeleteView(EventSlugMixin, IntermediateAdminView):
    """
    View: Confirmation page to delete confidential AK-related messages to orga

    Confirmation functionality provided by :class:`AKModel.metaviews.admin.IntermediateAdminView`
    """
    template_name = "admin/AKModel/message_delete.html"
    title = _("Delete AK Orga Messages")

    def get_orga_messages_for_event(self, event):
        """
        Get all orga messages for the given event
        """
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
    """
    View: Confirmation page to reset all manually specified interest values

    Confirmation functionality provided by :class:`AKModel.metaviews.admin.IntermediateAdminView`
    """
    title = _("Reset interest in AKs")
    model = AK
    confirmation_message = _("Interest of the following AKs will be set to not filled (-1):")
    success_message = _("Reset of interest in AKs successful.")

    def action(self, form):
        self.entities.update(interest=-1)


class AKAssignTrackView(IntermediateAdminActionView):
    """
    View: Immediate page to assign tracks in bulk

    General functionality flow provided by :class:`AKModel.metaviews.admin.IntermediateAdminView`
    """
    title = _("Assign AKs to track")
    model = AK
    confirmation_message = _("Assign the following AKs to the given track?")
    success_message = _("Assigned to track.")
    form_class = TrackAssignmentForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = AK.objects.get(pk=kwargs["initial"]["pks"].split(",")[0]).event
        return kwargs

    def action(self, form):
        event = self.entities[0].event
        if 'track' in form.cleaned_data and form.cleaned_data['track'] is not None:
            track = form.cleaned_data['track']
        else:
            new_track_name = form.cleaned_data['new_track']
            track = AKTrack.objects.create(event=event, name=new_track_name)
        self.entities.update(track=track)


class AKMoveToTrashView(IntermediateAdminActionView):
    """
    View: Confirmation page to move AKs to trash

    Confirmation functionality provided by :class:`AKModel.metaviews.admin.IntermediateAdminView`
    """
    title = _("Move AKs to trash")
    model = AK
    confirmation_message = _("Move the following AKs to trash?")
    success_message = _("Moved AKs to trash.")

    def action(self, form):
        for entity in self.entities:
            entity.move_to_trash()


class AKRestoreFromTrashView(IntermediateAdminActionView):
    """
    View: Confirmation page to restore AKs from trash

    Confirmation functionality provided by :class:`AKModel.metaviews.admin.IntermediateAdminView`
    """
    title = _("Restore AKs from trash")
    model = AK
    confirmation_message = _("Restore the following AKs from trash?")
    success_message = _("Restored AKs from trash.")

    def get_queryset(self, pks=None):
        """
        Get the queryset of objects to perform the action on
        """
        if pks is None:
            pks = self.request.GET['pks']
        return self.model.trash.filter(pk__in=pks.split(","))

    def action(self, form):
        for entity in self.entities:
            entity.restore_from_trash()


class AKResetInterestCounterView(IntermediateAdminActionView):
    """
    View: Confirmation page to reset all interest counters (online interest indication)

    Confirmation functionality provided by :class:`AKModel.metaviews.admin.IntermediateAdminView`
    """
    title = _("Reset AKs' interest counters")
    model = AK
    confirmation_message = _("Interest counter of the following AKs will be set to 0:")
    success_message = _("AKs' interest counters set back to 0.")

    def action(self, form):
        self.entities.update(interest_counter=0)
