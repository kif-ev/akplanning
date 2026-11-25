import csv

import django.db
from django.apps import apps
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import CreateView

from AKModel.forms import RoomBatchCreationForm, RoomBatchImportConfirmForm, RoomForm
from AKModel.metaviews.admin import AdminViewMixin, EventSlugMixin, IntermediateAdminView
from AKModel.models import StatusTrackingEntry
from AKModel.room_import import import_rooms, parse_rooms_csv
from AKModel.status_tracking import status_tracker

Progress = StatusTrackingEntry.Progress


class RoomCreationView(AdminViewMixin, CreateView):
    """
    Admin view: Create a room
    """
    form_class = RoomForm
    template_name = 'admin/AKModel/room_create.html'

    def get_success_url(self):
        print(self.request.POST['save_action'])
        if self.request.POST['save_action'] == 'save_add_another':
            return reverse_lazy('admin:room-new')
        if self.request.POST['save_action'] == 'save_continue':
            return reverse_lazy('admin:AKModel_room_change', kwargs={'object_id': self.room.pk})
        return reverse_lazy('admin:AKModel_room_changelist')

    def form_valid(self, form):
        self.room = form.save()  # pylint: disable=attribute-defined-outside-init

        # translatable string with placeholders, no f-string possible
        # pylint: disable=consider-using-f-string
        messages.success(self.request, _("Created Room '%(room)s'" % {'room': self.room}))

        return HttpResponseRedirect(self.get_success_url())


class RoomBatchCreationView(EventSlugMixin, IntermediateAdminView):
    """
    Admin view: Allow to create rooms in batch by inputing a CSV-formatted list of room details
    into a textbox or uploading a CSV file

    This is the first step of the import: After submitting, the data is validated and a preview of the rooms to create
    is shown together with all problems found in the data, the import itself has to be confirmed in a second step
    (see :class:`RoomBatchImportConfirmView`).
    Virtual rooms are supported if AKOnline is active, and users can specify that default availabilities
    (from event start to end) should be created for the rooms automatically
    """
    template_name = "admin/AKModel/import_rooms.html"
    form_class = RoomBatchCreationForm
    title = _("Import Rooms from CSV")

    def form_valid(self, form):
        text = form.cleaned_data["csv_text"]
        try:
            result = parse_rooms_csv(text, self.event)
        except ValidationError as e:
            for error in e.messages:
                form.add_error(None, error)
            return self.form_invalid(form)

        create_default_availabilities = form.cleaned_data["create_default_availabilities"]
        # Allow to correct the data directly on the preview page (also when it was uploaded as a file)
        edit_form = RoomBatchCreationForm(initial={
            "csv_data": text,
            "create_default_availabilities": create_default_availabilities,
        })
        confirm_form = RoomBatchImportConfirmForm(initial={
            "csv_data": text,
            "create_default_availabilities": create_default_availabilities,
        })
        return render(self.request, "admin/AKModel/import_rooms_preview.html", self.get_context_data(
                form=edit_form,
                confirm_form=confirm_form,
                result=result,
                create_default_availabilities=create_default_availabilities,
        ))


class RoomBatchImportConfirmView(EventSlugMixin, IntermediateAdminView):
    """
    Admin view: Second step of the room batch import (see :class:`RoomBatchCreationView`)

    Validates the data again (the database could have changed since the preview was shown)
    and creates all valid rooms in a single transaction
    """
    form_class = RoomBatchImportConfirmForm
    title = _("Import Rooms from CSV")

    def get(self, request, *args, **kwargs):
        # This view only handles confirmations, start the import from the beginning instead
        return redirect('admin:room-import', event_slug=self.event.slug)

    def get_success_url(self):
        return reverse_lazy('admin:event_status', kwargs={'event_slug': self.event.slug})

    def form_invalid(self, form):
        messages.add_message(self.request, messages.ERROR, _("No rooms imported"))
        return redirect('admin:room-import', event_slug=self.event.slug)

    def form_valid(self, form):
        try:
            result = parse_rooms_csv(form.cleaned_data["csv_data"], self.event)
        except ValidationError:
            return self.form_invalid(form)

        try:
            created_count = import_rooms(result, self.event, form.cleaned_data["create_default_availabilities"])
        except django.db.Error as e:
            error_message = _("Could not import rooms, no rooms were created: {e}").format(e=str(e))
            messages.add_message(self.request, messages.ERROR, error_message)
            self._record_progress(Progress.FAILED, error_message)
            return redirect('admin:room-import', event_slug=self.event.slug)

        details = []
        if result.errors:
            skipped_message = _("Skipped {count} line(s) with errors").format(
                    count=len({line for line, _error in result.errors}))
            messages.add_message(self.request, messages.WARNING, skipped_message)
            details.append(skipped_message)
        if created_count > 0:
            imported_message = _("Imported {count} room(s)").format(count=created_count)
            messages.add_message(self.request, messages.SUCCESS, imported_message)
            # Rooms are complete unless some of them were skipped and still have to be fixed and imported
            self._record_progress(Progress.IN_PROGRESS if result.errors else Progress.DONE,
                                  "\n".join([imported_message, *details]))
        else:
            messages.add_message(self.request, messages.WARNING, _("No rooms imported"))
        return super().form_valid(form)

    def _record_progress(self, progress: str, detail: str):
        """
        Track the progress of room creation (if the step is registered)

        :param progress: new progress of the step
        :param detail: detail text describing the import result
        """
        status_tracker.record_if_registered(self.event, "scheduling", "rooms", progress, detail=detail)


class RoomCSVTemplateView(EventSlugMixin, View):
    """
    Admin view: Download a CSV template for the room import

    The template contains a header row with all columns applicable for this event,
    i.e., the basic room fields, "url" if AKOnline is active, and one column per requirement of the event
    """

    def get(self, request, *args, **kwargs):
        self._load_event()
        columns = ["name", "location", "capacity"]
        if apps.is_installed("AKOnline"):
            columns.append("url")
        columns.extend(self.event.akrequirement_set.order_by('name').values_list('name', flat=True))

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{self.event.slug}-rooms-template.csv"'
        # Quote all fields so that column names containing spaces are not split by spreadsheet programs
        csv.writer(response, delimiter=";", quoting=csv.QUOTE_ALL).writerow(columns)
        return response
