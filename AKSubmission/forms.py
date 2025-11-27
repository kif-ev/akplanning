"""
Submission-specific forms
"""

import itertools
import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from AKModel.availability.forms import AvailabilitiesFormMixin
from AKModel.availability.models import Availability
from AKModel.models import AK, AKCategory, AKOrgaMessage, AKOwner, AKRequirement, AKSlot, AKType


class AKForm(AvailabilitiesFormMixin, forms.ModelForm):
    """
    Base form to add and edit AKs

    Contains suitable widgets for the different data types, restricts querysets (e.g., of requirements) to entries
    belonging to the event this AK belongs to.
    Prepares initial slot creation (by accepting multiple input formats and a list of slots to generate),
    automatically generate short names and wiki links if necessary

    Will be modified/used by :class:`AKSubmissionForm` (that allows to add slots and excludes links)
    and :class:`AKWishForm`
    """
    required_css_class = 'required'
    split_string = re.compile('[,;]')

    class Meta:
        model = AK
        fields = ['name',
                  'short_name',
                  'protocol_link',
                  'owners',
                  'description',
                  'goal',
                  'info',
                  'category',
                  'types',
                  'reso',
                  'present',
                  'requirements',
                  'conflicts',
                  'prerequisites',
                  'notes',
                  'event'
                  ]

        widgets = {
            'requirements': forms.CheckboxSelectMultiple,
            'types': forms.CheckboxSelectMultiple,
            'event': forms.HiddenInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial = {**self.initial, **kwargs['initial']}
        # Use better multiple select input for owners, conflicts and prerequisites
        if "owners" in self.fields:
            self.fields["owners"].widget.attrs = {'class': 'chosen-select'}
        self.fields["conflicts"].widget.attrs = {'class': 'chosen-select'}
        self.fields["prerequisites"].widget.attrs = {'class': 'chosen-select'}

        self.fields['category'].queryset = AKCategory.objects.filter(event=self.initial.get('event'))
        self.fields['types'].queryset = AKType.objects.filter(event=self.initial.get('event'))
        # Don't ask for types if there are no types configured for this event
        if self.fields['types'].queryset.count() == 0:
            self.fields.pop('types')
        self.fields['requirements'].queryset = AKRequirement.objects.filter(event=self.initial.get('event'))
        # Don't ask for requirements if there are no requirements configured for this event
        if self.fields['requirements'].queryset.count() == 0:
            self.fields.pop('requirements')
        self.fields['prerequisites'].queryset = AK.objects.filter(event=self.initial.get('event')).exclude(
                pk=self.instance.pk)
        self.fields['conflicts'].queryset = AK.objects.filter(event=self.initial.get('event')).exclude(
                pk=self.instance.pk)
        if "owners" in self.fields:
            self.fields['owners'].queryset = AKOwner.objects.filter(event=self.initial.get('event'))

    @staticmethod
    def _clean_duration(duration):
        """
        Clean/convert input format for the duration(s) of the slot(s)

        Handle different duration formats (h:mm and decimal comma instead of point)

        :param duration: raw input, either with ":", "," or "."
        :return: normalized duration (point-separated hour float)
        """
        if ":" in duration:
            h, m = duration.split(":")
            duration = int(h) + int(m) / 60
        if "," in str(duration):
            duration = float(duration.replace(",", "."))

        try:
            duration = float(duration)
        except ValueError as exc:
            raise ValidationError(
                    _('"%(duration)s" is not a valid duration'),
                    code='invalid',
                    params={'duration': duration},
            ) from exc

        return duration

    def clean(self):
        """
        Normalize/clean inputs

        Generate a (not yet used) short name if field was left blank,
        create a list of normalized slot durations

        :return: cleaned inputs
        """
        cleaned_data = super().clean()

        # Generate short name if not given
        short_name = self.cleaned_data["short_name"]
        if len(short_name) == 0:
            short_name = self.cleaned_data['name']
            # First try to split AK name at positions with semantic value (e.g., where the full name is separated
            # by a ':'), if not possible, do a hard cut at the maximum specified length
            short_name = short_name.partition(':')[0]
            short_name = short_name.partition(' - ')[0]
            short_name = short_name.partition(' (')[0]
            short_name = short_name[:AK._meta.get_field('short_name').max_length]
            # Check whether this short name already exists...
            for i in itertools.count(1):
                # ...and either use it...
                if not AK.objects.filter(short_name=short_name, event=self.cleaned_data["event"]).exists():
                    break
                # ... or postfix a number starting at 1 and growing until an unused short name is found
                digits = len(str(i))
                short_name = f'{short_name[:-(digits + 1)]}-{i}'
            cleaned_data["short_name"] = short_name

        # Get durations from raw durations field
        if "durations" in cleaned_data:
            cleaned_data["durations"] = [self._clean_duration(d) for d in self.cleaned_data["durations"].split()]
        return cleaned_data


class AKSubmissionForm(AKForm):
    """
    Form for Submitting new AKs

    Is a special variant of :class:`AKForm` that does not allow to manually edit wiki and protocol links and enforces
    the generation of at least one slot.
    """

    class Meta(AKForm.Meta):
        # Exclude fields again that were previously included in the parent class
        exclude = ['link', 'protocol_link']  # pylint: disable=modelform-uses-exclude
        widgets = AKForm.Meta.widgets | {
            'types': forms.CheckboxSelectMultiple(attrs={'checked': 'checked'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add field for durations (cleaning will be handled by parent class)
        self.fields["durations"] = forms.CharField(
                widget=forms.Textarea,
                label=_("Duration(s)"),
                help_text=_("Give the duration for your AK in hours, as a decimal number and without a unit symbol. "
                            "For every time your AK should take place, enter one line with one duration."),
                initial=self.initial.get('event').default_slot
        )

    def clean_availabilities(self):
        """
        Automatically improve availabilities entered.
        If the user did not specify availabilities assume the full event duration is possible
        :return: cleaned availabilities
        (either user input or one availability for the full length of the event if user input was empty)
        """
        availabilities = super().clean_availabilities()
        if len(availabilities) == 0:
            availabilities.append(Availability.with_event_length(event=self.cleaned_data["event"]))
        return availabilities


class AKWishForm(AKForm):
    """
    Form for submitting or editing wishes

    Is a special variant of :class:`AKForm` that does not allow to specify owner(s) or
    manually edit wiki and protocol links
    """

    class Meta(AKForm.Meta):
        # Exclude fields again that were previously included in the parent class
        exclude = ['owners', 'link', 'protocol_link']  # pylint: disable=modelform-uses-exclude
        widgets = AKForm.Meta.widgets | {
            'types': forms.CheckboxSelectMultiple(attrs={'checked': 'checked'}),
        }


class AKOwnerForm(forms.ModelForm):
    """
    Form to create/edit AK owners
    """
    required_css_class = 'required'

    class Meta:
        model = AKOwner
        fields = ['name', 'institution', 'link', 'event']
        widgets = {
            'event': forms.HiddenInput
        }


class AKDurationForm(forms.ModelForm):
    """
    Form to add an additional slot to a given AK
    """

    class Meta:
        model = AKSlot
        fields = ['duration', 'ak', 'event']
        widgets = {
            'ak': forms.HiddenInput,
            'event': forms.HiddenInput
        }


class AKOrgaMessageForm(forms.ModelForm):
    """
    Form to create a confidential message to the organizers  belonging to a given AK
    """

    class Meta:
        model = AKOrgaMessage
        fields = ['ak', 'text', 'event']
        widgets = {
            'ak': forms.HiddenInput,
            'event': forms.HiddenInput,
            'text': forms.Textarea,
        }
