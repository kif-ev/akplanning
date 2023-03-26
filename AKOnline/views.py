from django.contrib import messages
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _

from AKModel.metaviews import status_manager
from AKModel.metaviews.status import TemplateStatusWidget
from AKModel.views.room import RoomCreationView
from AKOnline.forms import RoomWithVirtualForm


class RoomCreationWithVirtualView(RoomCreationView):
    form_class = RoomWithVirtualForm
    template_name = 'admin/AKOnline/room_create_with_virtual.html'

    def form_valid(self, form):
        objects = form.save()
        self.room = objects['room']
        messages.success(self.request, _("Created Room '%(room)s'" % {'room': objects['room']}))
        if objects['virtual'] is not None:
            messages.success(self.request, _("Created related Virtual Room '%(vroom)s'" % {'vroom': objects['virtual']}))
        return HttpResponseRedirect(self.get_success_url())


@status_manager.register(name="event_virtual_rooms")
class EventVirtualRoomsWidget(TemplateStatusWidget):
    required_context_type = "event"
    title = _("Virtual Rooms")
    template_name = "admin/AKOnline/status/event_virtual_rooms.html"
