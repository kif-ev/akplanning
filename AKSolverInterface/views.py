import json
from collections import Counter

from django.apps import apps
from django.contrib import messages
from django.db.models import Count, Q
from django.db.models.query import QuerySet
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, TemplateView

from AKModel.metaviews.admin import (
    AdminViewMixin,
    EventSlugMixin,
    IntermediateAdminView,
    WizardViewMixin,
)
from AKModel.models import AK, Event
from AKScheduling.checks import aks_not_in_default_schedules, aks_with_unfulfillable_requirements
from AKSolverInterface.checks import participants_required_for_too_many_slots, required_preferences_without_overlap
from AKSolverInterface.forms import JSONExportControlForm, JSONScheduleImportForm
from AKSolverInterface.lookup import lookup_aks, lookup_participants, lookup_rooms, lookup_slots, lookup_timeslots
from AKSolverInterface.serializers import ExportEventSerializer


class SchedulingWizardMixin(WizardViewMixin):
    """
    Mixin for all views of the automatic scheduling workflow

    Defines title and steps of the wizard and provides the URLs of the previous and next step
    (as ``wizard_prev_url`` and ``wizard_next_url``) for navigation.
    The steps before the export step are checks, they can be skipped (see ``wizard_skip_checks_url``).
    Has to be combined with :class:`EventSlugMixin`.
    """
    # pylint: disable=too-few-public-methods
    wizard_title = _("Automatic Scheduling Workflow")
    wizard_steps = [
        _("Basic Checks"),
        _("Check: Room requirements"),
        _("Check: AK slots"),
        _("Check: Preferences"),
        _("Export"),
        _("Investigate issues"),
        _("Import"),
        _("Results"),
    ]
    # URL names of the views of the steps (same order as wizard_steps)
    wizard_url_names = [
        "admin:scheduling_wizard_checks",
        "admin:scheduling_wizard_requirements",
        "admin:scheduling_wizard_slots",
        "admin:scheduling_wizard_preferences",
        "admin:scheduling_wizard_export",
        "admin:scheduling_wizard_lookup",
        "admin:scheduling_wizard_import",
        "admin:scheduling_wizard_results",
    ]
    # Step of the export (all steps before are checks)
    wizard_export_step = 5

    # Possible results of a check (correspond to bootstrap colors)
    STATUS_OK = "success"
    STATUS_WARNING = "warning"
    STATUS_ERROR = "danger"

    @staticmethod
    def _format_duration(hours) -> str:
        """
        Format a duration given in hours as "H h" (full hours) or "H:MM h"

        :param hours: duration in hours
        :return: formatted duration
        :rtype: str
        """
        h, m = divmod(round(float(hours) * 60), 60)
        return f"{h} h" if m == 0 else f"{h}:{m:02d} h"

    def get_wizard_step_url(self, step: int) -> str | None:
        """
        Get the URL of the given (1-based) step of the wizard (all steps can be accessed directly)

        :param step: step to get the URL for
        :return: URL or None if there is no such step
        """
        if 1 <= step <= len(self.wizard_url_names):
            return reverse(self.wizard_url_names[step - 1], kwargs={"event_slug": self.event.slug})
        return None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["wizard_prev_url"] = self.get_wizard_step_url(self.wizard_step - 1)
        context["wizard_next_url"] = self.get_wizard_step_url(self.wizard_step + 1)
        context["wizard_is_check_step"] = self.wizard_step < self.wizard_export_step
        if context["wizard_is_check_step"]:
            context["wizard_skip_checks_url"] = self.get_wizard_step_url(self.wizard_export_step)
        return context


class AKJSONExportView(EventSlugMixin, AdminViewMixin, SchedulingWizardMixin, FormView):
    """
    View: Export all AK slots of this event in JSON format ordered by tracks

    Part of the automatic scheduling workflow (step: Export).
    The generated JSON can be copied or downloaded as file (client-side, without serializing it again).
    """

    template_name = "admin/AKSolverInterface/scheduling_wizard/export.html"
    model = Event
    form_class = JSONExportControlForm
    wizard_step = 5
    show_ignore_slot_category_mismatches_field = False

    def get_form_kwargs(self):
        form_kwargs = super().get_form_kwargs()
        form_kwargs["event"] = self.event
        return form_kwargs

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        # Needed to hide the category ignore field from form if empty/not computed
        context["show_ignore_slot_category_mismatches_field"] = self.show_ignore_slot_category_mismatches_field
        return context

    def produce_exceptions(self, form):
        """
        Identify AKs that cannot be placed (no overlap between availabilities and default slots both in general and matching category). This will then adjust the form accordingly.
        :param form: form to adjust
        """
        qs = self.event.ak_set.filter(category__in=form.cleaned_data["export_categories"])
        aks_no_default_slot, aks_no_default_slot_for_category = aks_not_in_default_schedules(self.event, qs)
        if aks_no_default_slot and len(aks_no_default_slot) > 0:
            messages.warning(
                    self.request,
                    _(
                            "The following AKs cannot be placed in any default slot: {aks_list}"
                    ).format(
                            aks_list=", ".join(f"{ak.name}" for ak in aks_no_default_slot)
                    )
            )
        if aks_no_default_slot_for_category and len(aks_no_default_slot_for_category) > 0:
            form.fields["ignore_slot_category_mismatches"].choices = [
                (ak.pk, f"{ak.name} ({ak.category})") for ak in aks_no_default_slot_for_category
            ]
            form.fields["ignore_slot_category_mismatches"].initial = form.fields[
                "ignore_slot_category_mismatches"].choices
            self.show_ignore_slot_category_mismatches_field = True

    def form_invalid(self, form):
        # Form will be shown both if valid and invalid (for re-adjustment of export params)
        self.produce_exceptions(form)
        context = self.get_context_data(form=form)
        self.try_producing_export(context, form)
        return self.render_to_response(context)

    def form_valid(self, form):
        # Form will be shown both if valid and invalid (for re-adjustment of export params)
        self.produce_exceptions(form)
        context = self.get_context_data(form=form)
        self.try_producing_export(context, form)
        return self.render_to_response(context)

    def try_producing_export(self, context, form):
        try:
            # Find AKs that are not wishes but nevertheless have no slots
            aks_without_slot = AK.objects.annotate(num_owners=Count('owners')).filter(event=self.event,
                                                                                      akslot__isnull=True,
                                                                                      category__in=form.cleaned_data[
                                                                                          "export_categories"],
                                                                                      num_owners__gt=0
                                                                                      ).all()

            aks_to_ignore_category_for = self.event.ak_set.filter(
                    pk__in=form.cleaned_data.get("ignore_slot_category_mismatches", [])
            ).all()
            if len(aks_to_ignore_category_for) > 0:
                messages.warning(
                        self.request,
                        _(
                                "Category constraints for slots of the following AKs were removed: {aks_list}"
                        ).format(
                                aks_list=", ".join(str(ak) for ak in aks_to_ignore_category_for)
                        )
                )

            if aks_without_slot.exists():
                messages.warning(
                        self.request,
                        _(
                                "The following AKs have no slot assigned to them "
                                "and are therefore not exported: {aks_list}"
                        ).format(
                                aks_list=", ".join(aks_without_slot.values_list("name", flat=True))
                        )
                )

            def _filter_slots_cb(queryset: QuerySet) -> QuerySet:
                queryset = queryset.prefetch_related("ak")
                if "export_tracks" in form.cleaned_data:
                    queryset = queryset.filter(
                            Q(ak__track__in=form.cleaned_data["export_tracks"])
                            | Q(ak__track__isnull=True)
                    )
                if "export_categories" in form.cleaned_data:
                    queryset = queryset.filter(
                            Q(ak__category__in=form.cleaned_data["export_categories"])
                            | Q(ak__category__isnull=True)
                    )
                if "export_types" in form.cleaned_data:
                    queryset = queryset.filter(
                            Q(ak__types__in=form.cleaned_data["export_types"])
                            | Q(ak__types__isnull=True)
                    )

                return queryset.distinct().all()

            def _filter_rooms_cb(queryset: QuerySet) -> QuerySet:
                queryset = queryset.all()
                if not queryset.exists():
                    messages.warning(self.request, _("No Rooms are exported"))
                return queryset

            def _filter_participants_cb(queryset: QuerySet) -> QuerySet:
                queryset = queryset.all()
                if not queryset.exists():
                    messages.warning(self.request, _("No real participants are exported"))
                return queryset

            serialized_event = ExportEventSerializer(
                    context["event"],
                    filter_slots_cb=_filter_slots_cb,
                    filter_rooms_cb=_filter_rooms_cb,
                    filter_participants_cb=_filter_participants_cb,
                    export_scheduled_aks_as_fixed=form.cleaned_data["export_scheduled_aks_as_fixed"],
                    export_preferences=form.cleaned_data["export_preferences"],
                    aks_to_ignore_category_for=set(aks_to_ignore_category_for),
            )
            serialized_event_data = serialized_event.data

            # check after serialization, as scheduled slots might have been removed during it
            if not serialized_event_data["aks"]:
                messages.warning(self.request, _("No AKSlots are exported"))
            if not serialized_event_data["timeslots"]["blocks"]:
                messages.warning(self.request, _("No timeslots are exported"))
            context["json_data_oneline"] = json.dumps(serialized_event_data, ensure_ascii=False)
            context["json_data"] = json.dumps(serialized_event_data, indent=2, ensure_ascii=False)
            context["is_valid"] = True
        except ValueError as ex:
            messages.add_message(
                    self.request,
                    messages.ERROR,
                    _("Exporting AKs for the solver failed! Reason: ") + str(ex),
            )


class AKScheduleJSONImportView(EventSlugMixin, SchedulingWizardMixin, IntermediateAdminView):
    """
    View: Import an AK schedule from a json file that can be pasted into this view.

    Part of the automatic scheduling workflow (step: Import).
    After a successful import, the number of imported slots (overall and per category) is stored in the session
    and the wizard continues with the results step (:class:`SchedulingWizardResultsView`).
    """

    template_name = "admin/AKSolverInterface/scheduling_wizard/import.html"
    form_class = JSONScheduleImportForm
    wizard_step = 7

    def form_valid(self, form):
        try:
            updated_slots = self.event.schedule_from_json_with_slots(
                    form.cleaned_data["data"],
                    check_for_data_inconsistency=False,  # TODO: Actually handle filtered export
            )
        except ValueError as ex:
            messages.add_message(
                    self.request,
                    messages.ERROR,
                    _("Importing an AK schedule failed! Reason: ") + str(ex),
            )
            # Stay on the import step to allow fixing the problem
            return redirect("admin:scheduling_wizard_import", self.event.slug)

        messages.add_message(
                self.request,
                messages.SUCCESS,
                _("Successfully imported {n} slot(s)").format(n=len(updated_slots)),
        )
        per_category = Counter(str(slot.ak.category) for slot in updated_slots)
        self.request.session[SchedulingWizardResultsView.session_key(self.event)] = {
            "total": len(updated_slots),
            "per_category": [{"category": name, "count": count} for name, count in sorted(per_category.items())],
        }
        return redirect("admin:scheduling_wizard_results", self.event.slug)


class SchedulingWizardChecksView(EventSlugMixin, AdminViewMixin, SchedulingWizardMixin, TemplateView):
    """
    Wizard view (automatic scheduling): Entry/Checks

    Shows the results of basic checks whether the event is ready for automatic scheduling
    (e.g., are there rooms and default slots?)
    """
    template_name = "admin/AKSolverInterface/scheduling_wizard/checks.html"
    wizard_step = 1

    def get_checks(self):
        """
        Perform basic checks

        :return: list of check results, each a dict with the keys
            title, status (see STATUS_* constants), message, and optionally link_url & link_text to fix problems
            as well as entries (list of dicts with text and url, e.g., the affected objects;
            not named "items" since that would collide with dict.items() in templates)
        :rtype: list[dict]
        """
        checks = []

        # Rooms (without rooms, no AK can be scheduled)
        room_count = self.event.room_set.count()
        checks.append({
            "title": _("Rooms"),
            "status": self.STATUS_OK if room_count > 0 else self.STATUS_ERROR,
            "message": _("{count} room(s) available").format(count=room_count) if room_count > 0
            else _("There are no rooms for this event yet. Automatic scheduling requires at least one room."),
            "link_url": reverse("admin:room-import", kwargs={"event_slug": self.event.slug}),
            "link_text": _("Import rooms"),
        })

        # Default slots (optional, otherwise the whole event duration is split into uniform slots)
        default_slot_count = self.event.defaultslot_set.count()
        checks.append({
            "title": _("Default Slots"),
            "status": self.STATUS_OK if default_slot_count > 0 else self.STATUS_WARNING,
            "message": _("{count} default slot(s) defined").format(count=default_slot_count) if default_slot_count > 0
            else _("There are no default slots for this event. AKs could hence be scheduled at any time "
                   "between start and end of the event (including nights)."),
            "link_url": reverse("admin:default-slots-editor", kwargs={"event_slug": self.event.slug}),
            "link_text": _("Edit Default Slots"),
        })

        # Default slots without categories (no AK can be placed in them unless its category is ignored for export)
        if default_slot_count > 0:
            uncategorized = self.event.defaultslot_set.filter(primary_categories__isnull=True).order_by("start")
            uncategorized_count = len(uncategorized)
            checks.append({
                "title": _("Categories of default slots"),
                "status": self.STATUS_OK if uncategorized_count == 0 else self.STATUS_WARNING,
                "message": _("All default slots have at least one primary category") if uncategorized_count == 0
                else _("{count} of {total} default slot(s) have no primary category. "
                       "AKs can only be placed in them if their category is ignored for the export.")
                .format(count=uncategorized_count, total=default_slot_count),
                "link_url": reverse("admin:AKModel_defaultslot_changelist") + f"?event__id__exact={self.event.pk}",
                "link_text": _("Set primary categories"),
                "entries": [
                    {
                        "text": f"{slot.start_simplified} - {slot.end_simplified}",
                        "url": reverse("admin:AKModel_defaultslot_change", args=[slot.pk]),
                    }
                    for slot in uncategorized
                ],
            })

        return checks

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["checks"] = self.get_checks()
        context["checks_passed"] = all(c["status"] != self.STATUS_ERROR for c in context["checks"])
        context["wizard_can_continue"] = context["checks_passed"]
        return context


class SchedulingWizardRequirementsView(EventSlugMixin, AdminViewMixin, SchedulingWizardMixin, TemplateView):
    """
    Wizard view (automatic scheduling): Room requirements

    Lists all AKs whose requirements are not fulfilled by any single room of the event
    (see :func:`AKScheduling.checks.aks_with_unfulfillable_requirements`).
    These AKs cannot be placed by the solver.
    """
    template_name = "admin/AKSolverInterface/scheduling_wizard/requirements.html"
    wizard_step = 2

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        aks_with_requirements = self.event.ak_set.filter(requirements__isnull=False).distinct()
        context["aks_with_requirements_count"] = aks_with_requirements.count()
        context["aks_unfulfillable_requirements"] = aks_with_unfulfillable_requirements(
                self.event, aks_with_requirements.select_related("category")
        )
        context["status"] = self.STATUS_WARNING if context["aks_unfulfillable_requirements"] else self.STATUS_OK
        return context


class SchedulingWizardSlotsView(EventSlugMixin, AdminViewMixin, SchedulingWizardMixin, TemplateView):
    """
    Wizard view (automatic scheduling): AK slots

    Checks for each AK whether its availabilities overlap long enough (at least the duration of its longest slot)
    with a default slot (see :func:`AKScheduling.checks.aks_not_in_default_schedules`).
    Distinguishes between AKs that do not fit into any default slot
    and AKs that only fit into default slots not intended for their category.
    """
    template_name = "admin/AKSolverInterface/scheduling_wizard/slots.html"
    wizard_step = 3

    def _with_slot_info(self, aks):
        """
        Add the durations of all slots (sorted descending, i.e., the longest slot relevant for the check comes first)
        and the lengths of all availabilities (sorted by start) to each AK for display

        Availabilities with an end not after their start are marked as invalid
        (such entries could be created by older versions of the availability form)

        :param aks: list of AKs (with prefetched akslot_set and availabilities)
        :return: list of dicts containing the AK and the additional information (as formatted strings)
        :rtype: list[dict]
        """
        return [
            {
                "ak": ak,
                "slot_lengths": [
                    self._format_duration(duration)
                    for duration in sorted((slot.duration for slot in ak.akslot_set.all()), reverse=True)
                ],
                "availability_lengths": [
                    {
                        "invalid": a.end <= a.start,
                        "length": self._format_duration((a.end - a.start).total_seconds() / 3600)
                        if a.end > a.start else "",
                    }
                    for a in sorted(ak.availabilities.all(), key=lambda a: a.start)
                ],
            }
            for ak in aks
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["has_default_slots"] = self.event.defaultslot_set.exists()
        if context["has_default_slots"]:
            aks_no_slot, aks_no_category_matching_slot = aks_not_in_default_schedules(
                    self.event, self.event.ak_set.select_related("category")
            )
            context["aks_no_slot"] = self._with_slot_info(aks_no_slot)
            context["aks_no_category_matching_slot"] = self._with_slot_info(aks_no_category_matching_slot)
            if aks_no_slot:
                context["status"] = self.STATUS_ERROR
            elif aks_no_category_matching_slot:
                context["status"] = self.STATUS_WARNING
            else:
                context["status"] = self.STATUS_OK
        return context


class SchedulingWizardPreferencesView(EventSlugMixin, AdminViewMixin, SchedulingWizardMixin, TemplateView):
    """
    Wizard view (automatic scheduling): Preferences

    Checks whether the preferences marking participants as required for AKs can be fulfilled:

    * Participants required for more AK slots than there are default slots
      (see :func:`AKSolverInterface.checks.participants_required_for_too_many_slots`)
    * Required preferences without a long enough overlap of the availabilities of AK and participant,
      both in a loose and a strict variant (see :func:`AKSolverInterface.checks.required_preferences_without_overlap`)
    """
    template_name = "admin/AKSolverInterface/scheduling_wizard/preferences.html"
    wizard_step = 4

    def _format_overlap_violations(self, violations):
        """
        Format the durations of the given overlap violations for display

        :param violations: list of violations as returned by required_preferences_without_overlap
        :return: list of dicts containing the preference and the formatted durations
        :rtype: list[dict]
        """
        return [
            {
                "preference": v["preference"],
                "longest_slot": self._format_duration(v["longest_slot"].total_seconds() / 3600),
                "longest_window": self._format_duration(v["longest_window"].total_seconds() / 3600),
            }
            for v in violations
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["has_default_slots"] = self.event.defaultslot_set.exists()

        # a) Participants required for more slots than there are default slots (only with default slots)
        if context["has_default_slots"]:
            context["too_many_required"] = participants_required_for_too_many_slots(self.event)
            context["too_many_required_status"] = (self.STATUS_WARNING if context["too_many_required"]
                                                   else self.STATUS_OK)

        # b) Overlap of AK and participant availabilities
        loose_violations, strict_violations = required_preferences_without_overlap(self.event)
        context["loose_violations"] = self._format_overlap_violations(loose_violations)
        context["loose_status"] = self.STATUS_ERROR if loose_violations else self.STATUS_OK
        if strict_violations is not None:
            context["strict_violations"] = self._format_overlap_violations(strict_violations)
            context["strict_status"] = self.STATUS_WARNING if strict_violations else self.STATUS_OK
        return context


class SchedulingWizardLookupView(EventSlugMixin, AdminViewMixin, SchedulingWizardMixin, TemplateView):
    """
    Wizard view (automatic scheduling): Investigate issues

    Allows quick lookups of the objects behind the IDs used in the solver export/output
    (AKs, AK slots, rooms, timeslots and participants).
    All necessary information is serialized into the page (see :mod:`AKSolverInterface.lookup`),
    the lookup itself is done in the browser without any API calls.
    """
    template_name = "admin/AKSolverInterface/scheduling_wizard/lookup.html"
    wizard_step = 6

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lookup_data = {
            "ak": lookup_aks(self.event),
            "slot": lookup_slots(self.event),
            "room": lookup_rooms(self.event),
            "participant": lookup_participants(self.event),
        }
        try:
            lookup_data["timeslot"] = lookup_timeslots(self.event)
        except ValueError as ex:
            # Timeslots cannot be generated (the export would fail for the same reason)
            lookup_data["timeslot"] = {}
            context["timeslot_error"] = str(ex)
        context["lookup_data"] = lookup_data
        # Labels of the types of objects (used both in the form and in the frontend code)
        context["lookup_labels"] = {
            "ak": _("AK"),
            "slot": _("AK slot"),
            "room": _("Room"),
            "timeslot": _("Timeslot (default slot)"),
            "participant": _("Participant"),
            "not_found": _("No object with this ID found."),
        }
        return context


class SchedulingWizardResultsView(EventSlugMixin, AdminViewMixin, SchedulingWizardMixin, TemplateView):
    """
    Wizard view (automatic scheduling): Results

    Shows the number of slots scheduled by the last import (overall and per category, stored in the session by
    :class:`AKScheduleJSONImportView`). If AKScheduling is installed, the scheduling statistics
    (line chart and numbers, see :mod:`AKScheduling.stats`) are shown and linked, otherwise a generic success page.
    """
    template_name = "admin/AKSolverInterface/scheduling_wizard/results.html"
    wizard_step = 8

    @staticmethod
    def session_key(event: Event) -> str:
        """
        Key used to store the results of the last import for the given event in the session
        """
        return f"scheduling_wizard_import_result_{event.pk}"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["import_result"] = self.request.session.get(self.session_key(self.event))
        context["scheduling_installed"] = apps.is_installed("AKScheduling")
        if context["scheduling_installed"]:
            # pylint: disable=import-outside-toplevel
            from AKScheduling.stats import scheduling_statistics, statistics_line_chart
            context["stats"] = scheduling_statistics(self.event)
            context["chart"] = statistics_line_chart(context["stats"])
        return context
