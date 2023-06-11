from django.contrib import messages
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _

from AKModel.metaviews import status_manager
from AKModel.metaviews.status import TemplateStatusWidget
from AKModel.views.room import RoomCreationView
from AKOnline.forms import RoomWithVirtualForm


class RoomCreationWithVirtualView(RoomCreationView):
    """
    View to create both rooms and optionally virtual rooms by filling one form
    """
    form_class = RoomWithVirtualForm
    template_name = 'admin/AKOnline/room_create_with_virtual.html'
    room = None

    def form_valid(self, form):
        # This will create the room and additionally a virtual room if the url field is not blank
        # objects['room'] will always a room instance afterwards, objects['virtual'] may be empty
        objects = form.save()
        self.room = objects['room']
        # Create a (translated) success message containing information about the created room
        messages.success(self.request, _("Created Room '%(room)s'" % {'room': objects['room']})) #pylint: disable=consider-using-f-string, line-too-long
        if objects['virtual'] is not None:
            # Create a (translated) success message containing information about the created virtual room
            messages.success(self.request, _("Created related Virtual Room '%(vroom)s'" % {'vroom': objects['virtual']})) #pylint: disable=consider-using-f-string, line-too-long
        return HttpResponseRedirect(self.get_success_url())


@status_manager.register(name="event_virtual_rooms")
class EventVirtualRoomsWidget(TemplateStatusWidget):
    """
    Status page widget to contain information about all virtual rooms belonging to the given event
    """
    required_context_type = "event"
    title = _("Virtual Rooms")
    template_name = "admin/AKOnline/status/event_virtual_rooms.html"
