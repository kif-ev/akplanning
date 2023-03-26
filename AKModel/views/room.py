import csv

import django.db
from django.apps import apps
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView

from AKModel.forms import RoomForm, RoomBatchCreationForm
from AKModel.metaviews.admin import AdminViewMixin, EventSlugMixin, IntermediateAdminView
from AKModel.models import Room


class RoomCreationView(AdminViewMixin, CreateView):
    form_class = RoomForm
    template_name = 'admin/AKModel/room_create.html'

    def get_success_url(self):
        print(self.request.POST['save_action'])
        if self.request.POST['save_action'] == 'save_add_another':
            return reverse_lazy('admin:room-new')
        elif self.request.POST['save_action'] == 'save_continue':
            return reverse_lazy('admin:AKModel_room_change', kwargs={'object_id': self.room.pk})
        else:
            return reverse_lazy('admin:AKModel_room_changelist')

    def form_valid(self, form):
        self.room = form.save()
        messages.success(self.request, _("Created Room '%(room)s'" % {'room': self.room}))
        return HttpResponseRedirect(self.get_success_url())


class RoomBatchCreationView(EventSlugMixin, IntermediateAdminView):
    form_class = RoomBatchCreationForm
    title = _("Import Rooms from CSV")

    def get_success_url(self):
        return reverse_lazy('admin:event_status', kwargs={'slug': self.event.slug})

    def form_valid(self, form):
        virtual_rooms_support = False
        created_count = 0

        rooms_raw_dict: csv.DictReader = form.cleaned_data["rooms"]

        if apps.is_installed("AKOnline") and "url" in rooms_raw_dict.fieldnames:
            virtual_rooms_support = True
            from AKOnline.models import VirtualRoom

        for raw_room in rooms_raw_dict:
            name = raw_room["name"]
            location = raw_room["location"] if "location" in rooms_raw_dict.fieldnames else ""
            capacity = raw_room["capacity"] if "capacity" in rooms_raw_dict.fieldnames else -1

            try:
                r = Room.objects.create(name=name,
                                    location=location,
                                    capacity=capacity,
                                    event=self.event)
                if virtual_rooms_support and raw_room["url"] != "":
                    VirtualRoom.objects.create(room=r,
                                               url=raw_room["url"])
                created_count += 1
            except django.db.Error as e:
                messages.add_message(self.request, messages.WARNING,
                                     _("Could not import room {name}: {e}").format(name=name, e=str(e)))

        if created_count > 0:
            messages.add_message(self.request, messages.SUCCESS,
                                 _("Imported {count} room(s)").format(count=created_count))
        else:
            messages.add_message(self.request, messages.WARNING, _("No rooms imported"))
        return super().form_valid(form)
