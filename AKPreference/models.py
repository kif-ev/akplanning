from django.db import models
from django.utils.translation import gettext_lazy as _

from AKModel.models import AK, AKRequirement, Event


class EventParticipant(models.Model):
    """ A participant describes a person taking part in an event."""

    class Meta:
        verbose_name = _('Participant')
        verbose_name_plural = _('Participants')
        ordering = ['name']

    name = models.CharField(max_length=64, blank=True, verbose_name=_('Nickname'),
                            help_text=_('Name to identify a participant by (in case of questions from the organizers)'))
    institution = models.CharField(max_length=128, blank=True, verbose_name=_('Institution'), help_text=_('Uni etc.'))

    event = models.ForeignKey(to=Event, on_delete=models.CASCADE, verbose_name=_('Event'),
                              help_text=_('Associated event'))

    requirements = models.ManyToManyField(to=AKRequirement, blank=True, verbose_name=_('Requirements'),
                                          help_text=_("Participant's Requirements"))

    def __str__(self) -> str:
        string = _("Anonymous {pk}").format(pk=self.pk) if not self.name else self.name
        if self.institution:
            string += f" ({self.institution})"
        return string

    @property
    def availabilities(self):
        """
        Get all availabilities associated to this EventParticipant
        :return: availabilities
        :rtype: QuerySet[Availability]
        """
        return "Availability".objects.filter(participant=self)

    def get_time_constraints(self) -> list[str]:
        """Construct list of required time constraint labels."""
        # local import to prevent cyclic import
        # pylint: disable=import-outside-toplevel
        from AKModel.availability.models import Availability

        avails = self.availabilities.all()
        participant_required_prefs = AKPreference.objects.filter(
            event=self.event,
            participant=self,
            preference=AKPreference.PreferenceLevel.REQUIRED,
        )

        if (
            avails
            and not Availability.is_event_covered(self.event, avails)
            and participant_required_prefs.exists()
        ):
            # participant has restricted availability and is actually required for AKs
            return [f"availability-participant-{self.pk}"]

        return []

    def get_room_constraints(self) -> list[str]:
        """Construct list of required room constraint labels."""
        return list(self.requirements.values_list("name", flat=True).order_by())

    @property
    def export_preferences(self):
        """Preferences of this participant with positive score."""
        return (
            AKPreference.objects
            .filter(
                participant=self, preference__gt=0
            )
            .order_by()
            .select_related('ak')
            .prefetch_related('ak__akslot_set')
        )


class AKPreference(models.Model):
    """Model representing the preference of a participant to an AK."""

    class Meta:
        verbose_name = _('AK Preference')
        verbose_name_plural = _('AK Preferences')
        unique_together = [['event', 'participant', 'ak']]
        ordering = ["-timestamp"]

    event = models.ForeignKey(to=Event, on_delete=models.CASCADE, verbose_name=_('Event'),
                              help_text=_('Associated event'))

    participant = models.ForeignKey(to=EventParticipant, on_delete=models.CASCADE, verbose_name=_('Participant'),
                              help_text=_('Participant this preference belongs to'))

    ak = models.ForeignKey(to=AK, on_delete=models.CASCADE, verbose_name=_('AK'),
                           help_text=_('AK this preference belongs to'))

    class PreferenceLevel(models.IntegerChoices):
        """
        Possible preference values
        """
        IGNORE = 0, _('Ignore')
        PREFER = 1, _('Interested')
        STRONG_PREFER = 2, _("Great interest")
        REQUIRED = 3, _("Required")

    preference = models.PositiveSmallIntegerField(verbose_name=_('Preference'), choices=PreferenceLevel.choices,
                                             help_text=_('Preference level for the AK'),
                                             blank=False,
                                             default=PreferenceLevel.IGNORE)

    timestamp = models.DateTimeField(auto_now_add=True, verbose_name=_('Timestamp'), help_text=_('Time of creation'))

    def __str__(self) -> str:
        return f"Preference {self.get_preference_display()} [of '{self.participant}' for AK '{self.ak}']"

    @property
    def required(self) -> bool:
        """Whether this preference is a 'REQUIRED'"""
        return self.preference == self.PreferenceLevel.REQUIRED

    @property
    def preference_score(self) -> int:
        """Score of this preference for the solver"""
        return self.preference if self.preference != self.PreferenceLevel.REQUIRED else -1
