from django.db import models
from django.utils.translation import gettext_lazy as _
from fontawesome_6.fields import IconField

from AKModel.models import Event


class DashboardButton(models.Model):
    """
    Model for a single dashboard button

    Allows to specify
    * a text (currently without possibility to translate),
    * a color (based on predefined design colors)
    * a url the button should point to (internal or external)
    * an icon (from the collection of fontawesome)

    Each button is associated with a single event and will be deleted when the event is deleted.
    """
    class Meta:
        verbose_name = _("Dashboard Button")
        verbose_name_plural = _("Dashboard Buttons")

    COLOR_CHOICES = (
        (0, "primary"),
        (1, "success"),
        (2, "info"),
        (3, "warning"),
        (4, "danger"),
    )

    text = models.CharField(max_length=50, blank=False, verbose_name=_("Text"),
                    help_text=_("Text that will be shown on the button"))
    url = models.URLField(blank=False, verbose_name=_("Link URL"), help_text=_("URL this button links to"))
    icon = IconField(default="external-link-alt", verbose_name=_("Icon"), help_text="Symbol represeting this button.")
    color = models.PositiveSmallIntegerField(choices=COLOR_CHOICES, default=0, blank=False,
                    verbose_name=_("Button Style"), help_text=_("Style (Color) of this button (bootstrap class)"))
    event = models.ForeignKey(to=Event, on_delete=models.CASCADE, blank=False, null=False,
                    verbose_name=_("Event"), help_text=_("Event this button belongs to"))

    def __str__(self):
        return f"{self.text} ({self.event})"
