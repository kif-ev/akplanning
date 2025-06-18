from django import forms
from django.utils.translation import gettext_lazy as _

from AKModel.availability.forms import AvailabilitiesFormMixin
from AKModel.availability.models import Availability
from AKModel.models import AKRequirement
from AKPreference.models import EventParticipant


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
