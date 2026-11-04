"""
Submission-specific forms
"""

import itertools
import re
from decimal import Decimal, InvalidOperation

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from AKModel.availability.forms import AvailabilitiesFormMixin
from AKModel.availability.models import Availability
from AKModel.models import AK, AKCategory, AKOrgaMessage, AKOwner, AKRequirement, AKSlot, AKType


def clean_slot_duration(raw_duration, event):
    """
    Clean/convert user input for the duration of a slot

    Handle different duration formats (h:mm and decimal comma instead of point), clamp durations longer than the
    event to the event length (see :attr:`AKModel.models.Event.max_slot_duration`), round to the precision of
    :attr:`AKModel.models.AKSlot.duration` and check the result against the validators of that field

    :param raw_duration: raw input, either with ":", "," or "."
    :param event: event the slot will belong to
    :return: tuple of the normalized duration (in hours) and a flag whether the duration had to be clamped
    :rtype: (Decimal, bool)
    :raises ValidationError: if the input cannot be converted into a meaningful duration
    """
    invalid = ValidationError(
            _('"%(duration)s" is not a valid duration'),
            code='invalid',
            params={'duration': raw_duration},
    )
    duration_field = AKSlot._meta.get_field('duration')

    # Parse input into a Decimal (in hours)
    try:
        if ":" in raw_duration:
            # Format h:mm (e.g., "1:30"), splitting fails with ValueError if there is more than one ":",
            # int() fails with ValueError for non-numeric parts.
            # Minutes are converted using Decimal to avoid float inaccuracies (e.g., 20 / 60)
            h, m = raw_duration.split(":")
            duration = int(h) + Decimal(int(m)) / 60
        else:
            # Decimal number, allow decimal comma (e.g., "1,5") in addition to decimal point.
            # Decimal() raises InvalidOperation (not ValueError) for strings that are no number
            duration = Decimal(raw_duration.replace(",", "."))
    except (ValueError, InvalidOperation) as exc:
        raise invalid from exc
    # Decimal also accepts "nan" and "inf" (and variants like "Infinity"), is_finite() is false for those.
    # Zero and negative values are no meaningful durations either
    if not duration.is_finite() or duration <= 0:
        raise invalid

    # Clamp durations longer than the event to the event length
    clamped = duration > event.max_slot_duration
    if clamped:
        duration = event.max_slot_duration

    # Round to the number of decimal places of the duration field (e.g., 1:20 = 1.3333... -> 1.33),
    # since the field validators would reject values with more decimal places.
    # Decimal(1).scaleb(-n) is 10^-n, i.e., 0.01 for two decimal places, and quantize() rounds to the
    # exponent of that value. This cannot fail, since the value is now between 0 and the event length
    duration = duration.quantize(Decimal(1).scaleb(-duration_field.decimal_places))

    # Apply the checks defined in the model (e.g., the minimum duration, which also rejects tiny values
    # that were rounded to 0 above)
    try:
        duration_field.run_validators(duration)
    except ValidationError as exc:
        raise invalid from exc

    return duration, clamped


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
        # Will be filled during cleaning: raw durations that exceeded the event length and were clamped
        self.clamped_durations = []
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

    def clean(self):
        """
        Normalize/clean inputs

        Generate a (not yet used) short name if field was left blank,
        create a list of normalized slot durations (durations longer than the event are clamped to the event length
        and remembered in :attr:`clamped_durations`)

        :return: cleaned inputs
        """
        cleaned_data = super().clean()
        self.clamped_durations = []

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
        # (if the event is invalid, the form is invalid anyway and durations cannot be clamped)
        if "durations" in cleaned_data and "event" in cleaned_data:
            durations = []
            errors = []
            # Every (non-empty) line is one duration, invalid lines are reported as a whole
            lines = [line.strip() for line in self.cleaned_data["durations"].splitlines()]
            for d in filter(None, lines):
                try:
                    duration, clamped = clean_slot_duration(d, cleaned_data["event"])
                except ValidationError as e:
                    errors.append(e)
                    continue
                # Remember clamped durations to be able to inform the user
                if clamped:
                    self.clamped_durations.append(d)
                durations.append(duration)
            if errors:
                # Mark the durations field as invalid (this also removes it from cleaned_data)
                # such that the user has to fix all invalid lines before the AK can be saved
                self.add_error("durations", errors)
            else:
                cleaned_data["durations"] = durations
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

    Accepts the same duration formats as :class:`AKSubmissionForm` and clamps durations longer than the event
    to the event length (see :func:`clean_slot_duration`)
    """

    # Use a text field to allow the same input formats as in the submission form (e.g., "1:30" or "1,5")
    duration = forms.CharField(label=AKSlot._meta.get_field('duration').verbose_name,
                               help_text=AKSlot._meta.get_field('duration').help_text)

    class Meta:
        model = AKSlot
        fields = ['duration', 'ak', 'event']
        widgets = {
            'ak': forms.HiddenInput,
            'event': forms.HiddenInput
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Will be filled during cleaning: raw duration if it exceeded the event length and was clamped
        self.clamped_durations = []

    def clean(self):
        """
        Normalize/clean duration input (see :func:`clean_slot_duration`)

        :return: cleaned inputs
        """
        cleaned_data = super().clean()
        self.clamped_durations = []
        # (if the event is invalid, the form is invalid anyway and the duration cannot be clamped)
        if "duration" in cleaned_data and "event" in cleaned_data:
            raw_duration = cleaned_data["duration"]
            try:
                duration, clamped = clean_slot_duration(raw_duration, cleaned_data["event"])
            except ValidationError as e:
                self.add_error("duration", e)
            else:
                cleaned_data["duration"] = duration
                if clamped:
                    self.clamped_durations.append(raw_duration)
        return cleaned_data


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
