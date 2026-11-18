from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _, ngettext

from AKModel.availability.forms import AvailabilitiesFormMixin
from AKModel.availability.models import Availability
from AKModel.models import AKRequirement
from AKPreference.checks import availability_overlap
from AKPreference.models import AKPreference, EventParticipant


def _format_duration(duration: timedelta) -> str:
    """
    Format a duration as "H h" (full hours) or "H:MM h"
    """
    h, m = divmod(round(duration.total_seconds() / 60), 60)
    return f"{h} h" if m == 0 else f"{h}:{m:02d} h"


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

    When a participant marks themselves as required for an AK, it is checked whether they are available long enough
    at the same time as the AK can take place (see :func:`AKPreference.checks.availability_overlap`).
    Otherwise, the formset cannot be saved and errors are shown for the affected AKs as well as a summary.
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

    def clean(self):
        """
        Make sure the participant is available long enough for all AKs they marked themselves as required for
        """
        super().clean()
        participant_availabilities = list(self.participant.availabilities.all())
        insufficient_count = 0

        for form in self.forms:
            cleaned_data = getattr(form, "cleaned_data", None)
            if not cleaned_data or cleaned_data.get("preference") != AKPreference.PreferenceLevel.REQUIRED:
                continue
            result = availability_overlap(self.participant.event, cleaned_data["ak"], participant_availabilities)
            if result is None or result.sufficient:
                continue

            insufficient_count += 1
            if result.longest_overlap.total_seconds() == 0:
                message = _("There is no time in which you are available and this AK can take place.")
            else:
                message = _("You are only available for {overlap} at a time when this AK can take place, "
                            "but its longest slot takes {slot}.").format(
                        overlap=_format_duration(result.longest_overlap),
                        slot=_format_duration(result.longest_slot),
                )
            form.add_error("preference", message)

        if insufficient_count > 0:
            raise ValidationError(ngettext(
                    "Your availabilities do not allow you to attend %(count)d AK you marked as required. "
                    "Please choose another preference for it or adjust your availabilities.",
                    "Your availabilities do not allow you to attend %(count)d AKs you marked as required. "
                    "Please choose other preferences for them or adjust your availabilities.",
                    insufficient_count,
            ) % {"count": insufficient_count})
