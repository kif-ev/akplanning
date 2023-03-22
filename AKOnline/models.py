from django.db import models
from django.utils.translation import gettext_lazy as _

from AKModel.models import Event, Room


class VirtualRoom(models.Model):
    """
    Add details about a virtual or hybrid version of a room to it
    """
    url = models.URLField(verbose_name=_("URL"), help_text=_("URL to the room or server"), blank=True)
    room = models.OneToOneField(Room, verbose_name=_("Room"), on_delete=models.CASCADE,
                                related_name='virtual', primary_key=True)

    class Meta:
        verbose_name = _('Virtual Room')
        verbose_name_plural = _('Virtual Rooms')

    @property
    def event(self):
        return self.room.event
