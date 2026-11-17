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
                                             verbose_name=_("Button Style"),
                                             help_text=_("Style (Color) of this button (bootstrap class)"))
    event = models.ForeignKey(to=Event, on_delete=models.CASCADE, blank=False, null=False,
                              verbose_name=_("Event"), help_text=_("Event this button belongs to"))

    def __str__(self):
        return f"{self.text} ({self.event})"


class EventFact(models.Model):
    """
    Model for a single manually maintained fact about an event

    Allows to specify facts that cannot be derived from the data stored in AKPlanning (e.g., the number of solver
    runs, since solving happens externally). These facts will be shown on the info page of the event together with
    the automatically computed facts.

    Each fact is associated with a single event and will be deleted when the event is deleted.
    """

    class Meta:
        verbose_name = _("Event Fact")
        verbose_name_plural = _("Event Facts")
        ordering = ['order', 'pk']

    title = models.CharField(max_length=100, blank=False, verbose_name=_("Title"),
                             help_text=_("Short description of the fact, e.g., 'Solver runs'"))
    value = models.CharField(max_length=100, blank=False, verbose_name=_("Value"),
                             help_text=_("Value of the fact (free text), e.g., '17'"))
    icon = IconField(default="fas,info-circle", verbose_name=_("Icon"), help_text=_("Symbol representing this fact"))
    order = models.PositiveSmallIntegerField(default=0, verbose_name=_("Order"),
                                             help_text=_("Facts with lower values are shown first"))
    event = models.ForeignKey(to=Event, on_delete=models.CASCADE, blank=False, null=False,
                              verbose_name=_("Event"), help_text=_("Event this fact belongs to"))

    def __str__(self):
        return f"{self.title}: {self.value} ({self.event})"
