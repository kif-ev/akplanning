from django.db import models
from django.utils.translation import gettext_lazy as _

from AKModel.models import Event, Room


class VirtualRoom(Room):
    """ A virtual room where an AK can be held.
    """
    url = models.URLField(verbose_name=_("URL"), help_text=_("URL to the room or server"), blank=True)

    class Meta:
        verbose_name = _('Virtual Room')
        verbose_name_plural = _('Virtual Rooms')
