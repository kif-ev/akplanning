import json
from typing import List

from django.contrib import messages
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, DetailView

from AKModel.availability.models import Availability
from AKModel.metaviews.admin import AdminViewMixin, FilterByEventSlugMixin, EventSlugMixin, IntermediateAdminView, \
    IntermediateAdminActionView
from AKModel.models import AKRequirement, AKSlot, Event, AKOrgaMessage, AK, Room, AKOwner


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
    """
    template_name = "admin/AKModel/ak_csv_export.html"
    model = AKSlot
    context_object_name = "slots"
    title = _("AK CSV Export")

    def get_queryset(self):
        return super().get_queryset().order_by("ak__track")


class AKJSONExportView(AdminViewMixin, FilterByEventSlugMixin, ListView):
    """
    View: Export all AK slots of this event in JSON format ordered by tracks
    """
    template_name = "admin/AKModel/ak_json_export.html"
    model = AKSlot
    context_object_name = "slots"
    title = _("AK JSON Export")

    def _test_slot_contained(self, slot: Availability, availabilities: List[Availability]) -> bool:
        return any(availability.contains(slot) for availability in availabilities)

    def _test_event_covered(self, availabilities: List[Availability]) -> bool:
        return not Availability.is_event_covered(self.event, availabilities)

    def _test_fixed_ak(self, ak_id, slot: Availability, ak_fixed: dict) -> bool:
        if not ak_id in ak_fixed:
            return False

        fixed_slot = Availability(self.event, start=ak_fixed[ak_id].start, end=ak_fixed[ak_id].end)
        return fixed_slot.overlaps(slot, strict=True)

    def _test_add_constraint(self, slot: Availability, availabilities: List[Availability]) -> bool:
        return (
            self._test_event_covered(availabilities)
            and self._test_slot_contained(slot, availabilities)
        )


    def get_queryset(self):
        return super().get_queryset().order_by("ak__track")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["participants"] = json.dumps([])

        rooms = Room.objects.filter(event=self.event)
        context["rooms"] = rooms

        # TODO: Configure magic number in event
        SLOTS_IN_AN_HOUR = 1

        timeslots = {
            "info": {"duration": (1.0 / SLOTS_IN_AN_HOUR), },
            "blocks": [],
            }

        for slot in context["slots"]:
            slot.slots_in_an_hour = SLOTS_IN_AN_HOUR

        ak_availabilities = {
            slot.ak.pk: Availability.union(slot.ak.availabilities.all())
            for slot in context["slots"]
        }
        room_availabilities = {
            room.pk: Availability.union(room.availabilities.all())
            for room in rooms
        }
        person_availabilities = {
            person.pk: Availability.union(person.availabilities.all())
            for person in AKOwner.objects.filter(event=self.event)
        }

        ak_fixed = {
            ak_id: values.get()
            for ak_id in ak_availabilities.keys()
            if (values := AKSlot.objects.select_related().filter(ak__pk=ak_id, fixed=True)).exists()
        }

        for block in self.event.default_time_slots(slots_in_an_hour=SLOTS_IN_AN_HOUR):
            current_block = []

            for slot_index, slot in block:
                time_constraints = []

                if self.event.reso_deadline is None or slot.end < self.event.reso_deadline:
                    time_constraints.append("resolution")

                time_constraints.extend([
                    f"availability-ak-{ak_id}"
                    for ak_id, availabilities in ak_availabilities.items()
                    if (
                        self._test_add_constraint(slot, availabilities)
                        or self._test_fixed_ak(ak_id, slot, ak_fixed)
                    )
                ])
                time_constraints.extend([
                    f"availability-person-{person_id}"
                    for person_id, availabilities in person_availabilities.items()
                    if self._test_add_constraint(slot, availabilities)
                ])
                time_constraints.extend([
                    f"availability-room-{room_id}"
                    for room_id, availabilities in room_availabilities.items()
                    if self._test_add_constraint(slot, availabilities)
                ])

                current_block.append({
                    "id": str(slot_index),
                    "info": {
                        "start": slot.simplified,
                    },
                    "fulfilled_time_constraints": time_constraints,
                    })

            timeslots["blocks"].append(current_block)

        context["timeslots"] = json.dumps(timeslots)

        info_dict = {
            "title": self.event.name,
            "slug": self.event.slug
        }
        for attr in ["contact_email", "place"]:
            if hasattr(self.event, attr) and getattr(self.event, attr):
                info_dict[attr] = getattr(self.event, attr)

        context["info_dict"] = json.dumps(info_dict)

        return context



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
