import json
from datetime import timedelta
from typing import List

from django.contrib import messages
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, DetailView

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

    def get_queryset(self):
        return super().get_queryset().order_by("ak__track")

    def get_context_data(self, **kwargs):
        from AKModel.availability.models import Availability

        SLOTS_IN_AN_HOUR = 1

        rooms = Room.objects.filter(event=self.event)
        participants = []
        timeslots = {
            "info": {"duration": (1.0 / SLOTS_IN_AN_HOUR), },
            "blocks": [],
            }

        context = super().get_context_data(**kwargs)
        context["rooms"] = rooms
        context["participants"] = json.dumps(participants)

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
            ak: values.get()
            for ak in ak_availabilities.keys()
            if (values := AKSlot.objects.select_related().filter(ak__pk=ak, fixed=True)).exists()
        }

        def _test_slot_contained(slot: Availability, availabilities: List[Availability]) -> bool:
            return any(availability.contains(slot) for availability in availabilities)

        def _test_event_covered(slot: Availability, availabilities: List[Availability]) -> bool:
            return not Availability.is_event_covered(self.event, availabilities)

        def _test_fixed_ak(ak, slot) -> bool:
            if not ak in ak_fixed:
                return False

            fixed_slot = Availability(self.event, start=ak_fixed[ak].start, end=ak_fixed[ak].end)
            return fixed_slot.overlaps(slot, strict=True)

        def _test_add_constraint(slot: Availability, availabilities: List[Availability]) -> bool:
            return _test_event_covered(slot, availabilities) and _test_slot_contained(slot, availabilities)

        for block in self.event.time_slots(slots_in_an_hour=SLOTS_IN_AN_HOUR):
            current_block = []

            for slot_index in block:
                slot = self.event.time_slot(time_slot_index=slot_index,
                                            slots_in_an_hour=SLOTS_IN_AN_HOUR)
                constraints = []

                if self.event.reso_deadline is None or slot.end < self.event.reso_deadline:
                    constraints.append("resolution")

                for ak, availabilities in ak_availabilities.items():
                    if _test_add_constraint(slot, availabilities) or _test_fixed_ak(ak, slot):
                        constraints.append(f"availability-ak-{ak}")

                for person, availabilities in person_availabilities.items():
                    if _test_add_constraint(slot, availabilities):
                        constraints.append(f"availability-person-{person}")

                for person, availabilities in room_availabilities.items():
                    if _test_add_constraint(slot, availabilities):
                        constraints.append(f"availability-room-{room}")

                current_block.append({
                    "id": slot_index,
                    "info": {
                        "start": slot.simplified,
                    },
                    "fulfilled_time_constraints": constraints,
                    })

            timeslots["blocks"].append(current_block)

        context["timeslots"] = json.dumps(timeslots)

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
