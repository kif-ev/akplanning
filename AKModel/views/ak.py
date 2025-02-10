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

    def _test_event_not_covered(self, availabilities: List[Availability]) -> bool:
        """Test if event is not covered by availabilities."""
        return not Availability.is_event_covered(self.event, availabilities)

    def _test_akslot_fixed_in_timeslot(self, ak_slot: AKSlot, timeslot: Availability) -> bool:
        """Test if an AKSlot is fixed to overlap a timeslot slot."""
        if not ak_slot.fixed or ak_slot.start is None:
            return False

        fixed_avail = Availability(event=self.event, start=ak_slot.start, end=ak_slot.end)
        return fixed_avail.overlaps(timeslot, strict=True)

    def _test_add_constraint(self, slot: Availability, availabilities: List[Availability]) -> bool:
        """Test if object is not available for whole event and may happen during slot."""
        return (
            self._test_event_not_covered(availabilities) and slot.is_covered(availabilities)
        )

    def _generate_time_constraints(
        self,
        avail_label: str,
        avail_dict: dict,
        timeslot_avail: Availability,
        prefix: str = "availability",
    ) -> list[str]:
        return [
            f"{prefix}-{avail_label}-{pk}"
            for pk, availabilities in avail_dict.items()
            if self._test_add_constraint(timeslot_avail, availabilities)
        ]

    def get_queryset(self):
        return super().get_queryset().order_by("ak__track")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data = {}

        rooms = Room.objects.filter(event=self.event)
        data["rooms"] = [r.as_json_dict() for r in rooms]

        timeslots = {
            "info": {"duration": float(self.event.export_slot)},
            "blocks": [],
            }

        ak_availabilities = {
            ak.pk: Availability.union(ak.availabilities.all())
            for ak in AK.objects.filter(event=self.event).all()
        }
        room_availabilities = {
            room.pk: Availability.union(room.availabilities.all())
            for room in rooms
        }
        person_availabilities = {
            person.pk: Availability.union(person.availabilities.all())
            for person in AKOwner.objects.filter(event=self.event)
        }

        blocks = list(self.event.discretize_timeslots())

        block_names = []

        for block_idx, block in enumerate(blocks):
            current_block = []

            if not block:
                continue

            block_start = block[0].avail.start.astimezone(self.event.timezone)
            block_end = block[-1].avail.end.astimezone(self.event.timezone)

            start_day = block_start.strftime("%A, %d. %b")
            if block_start.date() == block_end.date():
                # same day
                time_str = block_start.strftime("%H:%M") + " – " + block_end.strftime("%H:%M")
            else:
                # different days
                time_str = block_start.strftime("%a %H:%M") + " – " + block_end.strftime("%a %H:%M")
            block_names.append([start_day, time_str])

            block_timeconstraints = [f"notblock{idx}" for idx in range(len(blocks)) if idx != block_idx]

            for timeslot in block:
                time_constraints = []
                # if reso_deadline is set and timeslot ends before it,
                #   add fulfilled time constraint 'resolution'
                if self.event.reso_deadline is None or timeslot.avail.end < self.event.reso_deadline:
                    time_constraints.append("resolution")

                # add fulfilled time constraints for all AKs that cannot happen during full event
                time_constraints.extend(
                    self._generate_time_constraints("ak", ak_availabilities, timeslot.avail)
                )

                # add fulfilled time constraints for all persons that are not available for full event
                time_constraints.extend(
                    self._generate_time_constraints("person", person_availabilities, timeslot.avail)
                )

                # add fulfilled time constraints for all rooms that are not available for full event
                time_constraints.extend(
                    self._generate_time_constraints("room", room_availabilities, timeslot.avail)
                )

                # add fulfilled time constraints for all AKSlots fixed to happen during timeslot
                time_constraints.extend([
                    f"fixed-akslot-{slot.id}"
                    for slot in AKSlot.objects.filter(event=self.event, fixed=True)
                                              .exclude(start__isnull=True)
                    if self._test_akslot_fixed_in_timeslot(slot, timeslot.avail)
                ])

                time_constraints.extend(timeslot.constraints)
                time_constraints.extend(block_timeconstraints)

                current_block.append({
                    "id": timeslot.idx,
                    "info": {
                        "start": timeslot.avail.start.astimezone(self.event.timezone).strftime("%Y-%m-%d %H:%M"),
                        "end": timeslot.avail.end.astimezone(self.event.timezone).strftime("%Y-%m-%d %H:%M"),
                    },
                    "fulfilled_time_constraints": time_constraints,
                    })

            timeslots["blocks"].append(current_block)

        timeslots["info"]["blocknames"] = block_names

        info_dict = {
            "title": self.event.name,
            "slug": self.event.slug
        }

        for attr in ["contact_email", "place"]:
            if hasattr(self.event, attr) and getattr(self.event, attr):
                info_dict[attr] = getattr(self.event, attr)

        data["timeslots"] = timeslots
        data["info"] = info_dict
        data["participants"] = []
        data["aks"] = [ak.as_json_dict() for ak in context["slots"]]

        context["json_data_oneline"] = json.dumps(data)
        context["json_data"] = json.dumps(data, indent=2)

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
