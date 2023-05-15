from django.contrib import messages
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _

from AKModel.views import AdminViewMixin, RoomCreationView
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
