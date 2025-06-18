import json

from django.contrib import messages
from django.db.models import Q
from django.db.models.query import QuerySet
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, FormView

from AKModel.metaviews.admin import (
    AdminViewMixin,
    EventSlugMixin,
    IntermediateAdminView,
)
from AKModel.models import AK, Event
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

    def get_template_names(self):
        if self.request.method == "POST":
            return ["admin/AKSolverInterface/ak_json_export.html"]
        else:
            return ["admin/AKSolverInterface/ak_json_export_control.html"]

    def get_form_kwargs(self):
        form_kwargs = super().get_form_kwargs()
        form_kwargs["event"] = self.event
        return form_kwargs

    def form_valid(self, form):
        context = self.get_context_data()
        try:
            aks_without_slot = AK.objects.filter(event=self.event, akslot__isnull=True).all()
            if aks_without_slot.exists():
                messages.warning(
                    self.request,
                    _("The following AKs have no slot assigned to them and are therefore not exported: {aks_list}").format(
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

                queryset = queryset.all()
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

        # if serialization failed in `get_context_data` we redirect to
        #   the status page and show a message instead
        if not context.get("is_valid", False):
            return redirect("admin:event_status", context["event"].slug)
        return self.render_to_response(context)


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
                form.cleaned_data["data"]
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
