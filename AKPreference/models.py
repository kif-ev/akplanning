import uuid
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Exists, OuterRef
from django.utils.translation import gettext_lazy as _

from AKModel.models import AK, AKOwner, AKRequirement, Event


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

    uuid = models.UUIDField(unique=True, verbose_name=_('UUID'), default=uuid.uuid4,
                            help_text=_('Unique and non-guessable identifier for this participant'))

    ak_owner = models.ForeignKey(to=AKOwner, on_delete=models.SET_NULL, blank=True, null=True,
                                 verbose_name=_('AK owner (optional)'),
                                 help_text=_('Optional: If you own AKs yourself, you can select your AK owner '
                                             'name here. If you do, the times of the AKs you own will be treated '
                                             'as bad times for the AKs you would like to attend and your '
                                             'availabilities will be used when scheduling the AKs you own.'))

    def __str__(self) -> str:
        string = _("Anonymous {pk}").format(pk=self.pk) if not self.name else self.name
        if self.institution:
            string += f" ({self.institution})"
        string += f" [{self.uuid}]"
        return string

    def clean(self):
        super().clean()
        if self.ak_owner is not None and self.event_id is not None and self.ak_owner.event_id != self.event_id:
            raise ValidationError({"ak_owner": _("The AK owner must belong to the same event as the participant.")})

    @property
    def owned_aks(self):
        """AKs of the AK owner this participant is linked to (none if not linked)"""
        if self.ak_owner_id is None:
            return AK.objects.none()
        return AK.objects.filter(event=self.event, owners=self.ak_owner_id)

    @property
    def has_required_preferences(self) -> bool:
        """Whether this participant has 'Required' preferences (no longer selectable) for AKs that are not trashed"""
        return self.akpreference_set.filter(
                preference=AKPreference.PreferenceLevel.REQUIRED, ak__trashed_at__isnull=True,
        ).exists()

    def get_room_constraints(self) -> list[str]:
        """Construct list of required room constraint labels."""
        return list(self.requirements.values_list("name", flat=True).order_by())

    @property
    def export_preferences(self):
        """Preferences of this participant with positive score (ignoring trashed AKs)."""
        return (
            AKPreference.objects
            .filter(
                    participant=self, preference__gt=0, ak__trashed_at__isnull=True
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
        # No longer selectable in the preference poll (replaced by linking participants to AK owners),
        # but existing preferences are kept and still exported as hard constraints
        REQUIRED = 3, _("Required")

    preference = models.PositiveSmallIntegerField(verbose_name=_('Preference'), choices=PreferenceLevel.choices,
                                                  help_text=_('Preference level for the AK'),
                                                  blank=False,
                                                  default=PreferenceLevel.IGNORE)

    timestamp = models.DateTimeField(auto_now_add=True, verbose_name=_('Timestamp'), help_text=_('Time of creation'))

    def __str__(self) -> str:
        return f"Preference {self.get_preference_display()} [of '{self.participant}' for AK '{self.ak}']"

    @staticmethod
    def for_owned_ak() -> Exists:
        """Expression that is true for preferences for AKs owned by the AK owner linked to their participant.

        Such preferences can neither be entered in the poll nor are they exported,
        but they may exist if they were entered before the participant was linked to the AK owner
        or before the AK owner was added to the AK. They are kept in case the link is removed again.
        """
        return Exists(AK.objects.filter(pk=OuterRef("ak_id"), owners=OuterRef("participant__ak_owner")))

    @property
    def required(self) -> bool:
        """Whether this preference is a 'REQUIRED'"""
        return self.preference == self.PreferenceLevel.REQUIRED

    @property
    def preference_score(self) -> int:
        """Score of this preference for the solver"""
        return self.preference if self.preference != self.PreferenceLevel.REQUIRED else -1
