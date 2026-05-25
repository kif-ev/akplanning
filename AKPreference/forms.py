from django import forms

from AKModel.availability.forms import AvailabilitiesFormMixin
from AKModel.availability.models import Availability
from AKModel.models import AKRequirement
from AKPreference.models import AKPreference, EventParticipant


class EventParticipantForm(AvailabilitiesFormMixin, forms.ModelForm):
    """Form to add EventParticipants"""

    required_css_class = "required"

    class Meta:
        model = EventParticipant
        fields = [
            "name",
            "institution",
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
        fields = '__all__'
        widgets = {
            "event": forms.HiddenInput,
            "participant": forms.HiddenInput,
            "ak": forms.HiddenInput,
            "preference": forms.RadioSelect,
        }


class PreferenceFormSet(forms.BaseModelFormSet):
    """
    Formset to control all lines to enter preferences for a given participant and category
    """

    def __init__(self, *args, **kwargs):
        self.participant = kwargs.pop("participant")
        self.category = kwargs.pop("category")
        super().__init__(*args, **kwargs)

    def get_queryset(self):
        # Override queryset to only show existing preferences of the given participant and category
        # Other options will be added as "extras" in the view
        if not hasattr(self, "_queryset"):
            self._queryset = (super().get_queryset().filter(participant=self.participant, ak__category=self.category)
                              .select_related('ak')
                              .order_by('ak'))
        return self._queryset
