import json

from django.contrib import messages
from django.db.models import Q, Count
from django.db.models.query import QuerySet
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView

from AKModel.metaviews.admin import (
    AdminViewMixin,
    EventSlugMixin,
    IntermediateAdminView,
)
from AKModel.models import AK, Event
from AKScheduling.checks import aks_not_in_default_schedules
from AKSolverInterface.forms import JSONExportControlForm, JSONScheduleImportForm
from AKSolverInterface.serializers import ExportEventSerializer


class AKJSONExportView(EventSlugMixin, AdminViewMixin, FormView):
    """
    View: Export all AK slots of this event in JSON format ordered by tracks
    """

    template_name = "admin/AKSolverInterface/ak_json_export.html"
    model = Event
    form_class = JSONExportControlForm
    title = _("AK JSON Export")
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
            form.fields["ignore_slot_category_mismatches"].initial = form.fields["ignore_slot_category_mismatches"].choices
            self.show_ignore_slot_category_mismatches_field = True
        print(form.fields["ignore_slot_category_mismatches"].choices)

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
                                                 category__in=form.cleaned_data["export_categories"],
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

                queryset = queryset.distinct().all()
                if not queryset.exists():
                    messages.warning(
                            self.request,
                            _("No AKSlots are exported"),
                    )

                return queryset

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


class AKScheduleJSONImportView(EventSlugMixin, IntermediateAdminView):
    """
    View: Import an AK schedule from a json file that can be pasted into this view.
    """

    template_name = "admin/AKSolverInterface/import_json.html"
    form_class = JSONScheduleImportForm
    title = _("AK Schedule JSON Import")

    def form_valid(self, form):
        try:
            number_of_slots_changed = self.event.schedule_from_json(
                    form.cleaned_data["data"],
                    check_for_data_inconsistency=False,  # TODO: Actually handle filtered export
            )
            messages.add_message(
                    self.request,
                    messages.SUCCESS,
                    _("Successfully imported {n} slot(s)").format(
                            n=number_of_slots_changed
                    ),
            )
        except ValueError as ex:
            messages.add_message(
                    self.request,
                    messages.ERROR,
                    _("Importing an AK schedule failed! Reason: ") + str(ex),
            )

        return redirect("admin:event_status", self.event.slug)
