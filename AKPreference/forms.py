from django import forms
from django.core.exceptions import ValidationError
from django.forms.utils import ErrorDict

from AKModel.availability.forms import AvailabilitiesFormMixin
from AKModel.availability.models import Availability
from AKModel.models import AKOwner, AKRequirement
from AKPreference.models import AKPreference, EventParticipant


class EventParticipantForm(AvailabilitiesFormMixin, forms.ModelForm):
    """Form to add EventParticipants"""

    required_css_class = "required"

    class Meta:
        model = EventParticipant
        fields = [
            "name",
            "institution",
            "ak_owner",
            "requirements",
            "event",
        ]
        widgets = {
            "requirements": forms.CheckboxSelectMultiple,
            "event": forms.HiddenInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial = {**self.initial, **kwargs["initial"]}

        self.fields["requirements"].queryset = AKRequirement.objects.filter(
                event=self.initial.get("event"), relevant_for_participants=True
        )
        # Don't ask for requirements if there are no requirements configured for this event
        if self.fields["requirements"].queryset.count() == 0:
            self.fields.pop("requirements")

        self.fields["ak_owner"].queryset = AKOwner.objects.filter(event=self.initial.get("event"))
        # Don't ask for the AK owner if there are no AK owners for this event
        if self.fields["ak_owner"].queryset.count() == 0:
            self.fields.pop("ak_owner")

    def clean_availabilities(self):
        """
        Automatically improve availabilities entered.
        If the user did not specify availabilities assume the full event duration is possible
        :return: cleaned availabilities
        (either user input or one availability for the full length of the event if user input was empty)
        """
        availabilities = super().clean_availabilities()
        if len(availabilities) == 0:
            availabilities.append(
                    Availability.with_event_length(event=self.cleaned_data["event"])
            )
        return availabilities


class PreferenceForm(forms.ModelForm):
    """
    Form for each preference
    """

    class Meta:
        model = AKPreference
        # Event and participant are not submitted but set by the formset, so they cannot be changed by the user
        fields = ["ak", "preference"]
        widgets = {
            "ak": forms.HiddenInput,
            "preference": forms.RadioSelect,
        }

    # Set by the formset for rows whose AK is no longer available (e.g., because it was moved to the trash
    # after the form was displayed). Such rows are neither validated nor saved
    stale = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 'Required' can no longer be selected, but is kept as option for preferences that already have it
        # to not drop them when the participant saves their preferences again
        if self.instance.preference != AKPreference.PreferenceLevel.REQUIRED:
            self.fields["preference"].choices = [
                choice for choice in self.fields["preference"].choices
                if choice[0] != AKPreference.PreferenceLevel.REQUIRED
            ]

    def validate_unique(self):
        # Event and participant are not part of the form, but must be included in the uniqueness check,
        # e.g., if a preference for the same AK was saved from another tab in the meantime
        exclude = self._get_validation_exclusions() - {"event", "participant"}
        try:
            self.instance.validate_unique(exclude=exclude)
        except ValidationError as e:
            self._update_errors(e)

    def full_clean(self):
        if self.stale:
            self._errors = ErrorDict()
            # pylint: disable-next=attribute-defined-outside-init
            self.cleaned_data = {}
            return
        super().full_clean()


class PreferenceFormSet(forms.BaseModelFormSet):
    """
    Formset to control all lines to enter preferences for a given participant and category

    AKs owned by the participant (see :attr:`AKPreference.models.EventParticipant.owned_aks`) are not rated,
    since the participant is automatically required for them in the export
    """

    def __init__(self, *args, **kwargs):
        self.participant = kwargs.pop("participant")
        self.category = kwargs.pop("category")
        super().__init__(*args, **kwargs)
        self._owned_ak_pks = {str(pk) for pk in self.participant.owned_aks.values_list("pk", flat=True)}
        self._available_ak_pks = {
                                     str(pk) for pk in self.category.ak_set.values_list("pk", flat=True)
                                 } - self._owned_ak_pks

    def _construct_form(self, i, **kwargs):
        form = super()._construct_form(i, **kwargs)
        form.instance.participant = self.participant
        form.instance.event = self.participant.event
        # Submitted rows may refer to AKs that were trashed in the meantime
        # or that the participant became responsible for (e.g., by linking their AK owner in another tab)
        if self.is_bound:
            form.stale = str(form["ak"].value()) not in self._available_ak_pks
        return form

    def _submitted_stale_forms(self):
        """
        Stale rows of the submitted data

        Rows without any submitted AK are ignored: They belong to stale rows of an earlier submission
        that were not rendered again and thus were already reported back then
        """
        return [f for f in self.forms if f.stale and f["ak"].value() not in f.fields["ak"].empty_values]

    @property
    def has_stale_forms(self):
        """
        Did the submitted data contain rows for AKs that are no longer available?
        """
        return any(str(f["ak"].value()) not in self._owned_ak_pks for f in self._submitted_stale_forms())

    @property
    def has_owned_stale_forms(self):
        """
        Did the submitted data contain rows for AKs the participant is responsible for by now?
        """
        return any(str(f["ak"].value()) in self._owned_ak_pks for f in self._submitted_stale_forms())

    def get_queryset(self):
        # Override queryset to only show existing preferences of the given participant and category
        # Other options will be added as "extras" in the view
        if not hasattr(self, "_queryset"):
            # pylint: disable-next=attribute-defined-outside-init
            self._queryset = (super().get_queryset().filter(participant=self.participant, ak__category=self.category,
                                                            ak__trashed_at__isnull=True)
                              .exclude(ak__in=self.participant.owned_aks)
                              .select_related('ak')
                              .order_by('ak'))
        return self._queryset
