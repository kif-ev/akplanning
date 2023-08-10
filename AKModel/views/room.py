import csv

import django.db
from django.apps import apps
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView

from AKModel.availability.models import Availability
from AKModel.forms import RoomForm, RoomBatchCreationForm
from AKModel.metaviews.admin import AdminViewMixin, EventSlugMixin, IntermediateAdminView
from AKModel.models import Room


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
    Admin action: Allow to create rooms in batch by inputing a CSV-formatted list of room details into a textbox

    This offers the input form, supports creation of virtual rooms if AKOnline is active, too,
    and users can specify that default availabilities (from event start to end) should be created for the rooms
    automatically
    """
    form_class = RoomBatchCreationForm
    title = _("Import Rooms from CSV")

    def get_success_url(self):
        return reverse_lazy('admin:event_status', kwargs={'event_slug': self.event.slug})

    def form_valid(self, form):
        virtual_rooms_support = False
        create_default_availabilities = form.cleaned_data["create_default_availabilities"]
        created_count = 0

        rooms_raw_dict: csv.DictReader = form.cleaned_data["rooms"]

        # Prepare creation of virtual rooms if there is information (an URL) in the data and the AKOnline app is active
        if apps.is_installed("AKOnline") and "url" in rooms_raw_dict.fieldnames:
            virtual_rooms_support = True
            # pylint: disable=import-outside-toplevel
            from AKOnline.models import VirtualRoom

        # Loop over all inputs
        for raw_room in rooms_raw_dict:
            # Gather the relevant information (most fields can be empty)
            name = raw_room["name"]
            location = raw_room["location"] if "location" in rooms_raw_dict.fieldnames else ""
            capacity = raw_room["capacity"] if "capacity" in rooms_raw_dict.fieldnames else -1

            try:
                # Try to create a room (catches cases where the room name contains keywords or symbols that the
                # database cannot handle (.e.g., special UTF-8 characters)
                r = Room.objects.create(name=name,
                                    location=location,
                                    capacity=capacity,
                                    event=self.event)

                # and if necessary an associated virtual room, too
                if virtual_rooms_support and raw_room["url"] != "":
                    VirtualRoom.objects.create(room=r,
                                               url=raw_room["url"])

                # If user requested default availabilities, create them
                if create_default_availabilities:
                    a = Availability.with_event_length(event=self.event, room=r)
                    a.save()
                created_count += 1
            except django.db.Error as e:
                messages.add_message(self.request, messages.WARNING,
                                     _("Could not import room {name}: {e}").format(name=name, e=str(e)))

        # Inform the user about the rooms created
        if created_count > 0:
            messages.add_message(self.request, messages.SUCCESS,
                                 _("Imported {count} room(s)").format(count=created_count))
        else:
            messages.add_message(self.request, messages.WARNING, _("No rooms imported"))
        return super().form_valid(form)
