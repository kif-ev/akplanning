import itertools
import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from AKModel.availability.forms import AvailabilitiesFormMixin
from AKModel.availability.models import Availability
from AKModel.models import AK, AKOwner, AKCategory, AKRequirement, AKSlot, AKOrgaMessage, Event


class AKForm(AvailabilitiesFormMixin, forms.ModelForm):
    required_css_class = 'required'
    split_string = re.compile('[,;]')

    class Meta:
        model = AK
        fields = ['name',
                  'short_name',
                  'link',
                  'protocol_link',
                  'owners',
                  'description',
                  'category',
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
        self.fields['requirements'].queryset = AKRequirement.objects.filter(event=self.initial.get('event'))
        self.fields['prerequisites'].queryset = AK.objects.filter(event=self.initial.get('event')).exclude(
            pk=self.instance.pk)
        self.fields['conflicts'].queryset = AK.objects.filter(event=self.initial.get('event')).exclude(
            pk=self.instance.pk)
        if "owners" in self.fields:
            self.fields['owners'].queryset = AKOwner.objects.filter(event=self.initial.get('event'))

    @staticmethod
    def _clean_duration(duration):
        # Handle different duration formats (h:mm and decimal comma instead of point)
        if ":" in duration:
            h, m = duration.split(":")
            duration = int(h) + int(m) / 60
        if "," in str(duration):
            duration = float(duration.replace(",", "."))

        try:
            float(duration)
        except ValueError:
            raise ValidationError(
                _('"%(duration)s" is not a valid duration'),
                code='invalid',
                params={'duration': duration},
            )

        return duration

    def clean(self):
        cleaned_data = super().clean()

        # Generate short name if not given
        short_name = self.cleaned_data["short_name"]
        if len(short_name) == 0:
            short_name = self.cleaned_data['name']
            short_name = short_name.partition(':')[0]
            short_name = short_name.partition(' - ')[0]
            short_name = short_name.partition(' (')[0]
            short_name = short_name[:AK._meta.get_field('short_name').max_length]
            for i in itertools.count(1):
                if not AK.objects.filter(short_name=short_name, event=self.cleaned_data["event"]).exists():
                    break
                digits = len(str(i))
                short_name = '{}-{}'.format(short_name[:-(digits + 1)], i)
            cleaned_data["short_name"] = short_name

        # Generate wiki link
        if self.cleaned_data["event"].base_url:
            link = self.cleaned_data["event"].base_url + self.cleaned_data["name"].replace(" ", "_")
            # Truncate links longer than 200 characters (default length of URL fields in django)
            self.cleaned_data["link"] = link[:200]

        # Get durations from raw durations field
        if "durations" in cleaned_data:
            cleaned_data["durations"] = [self._clean_duration(d) for d in self.cleaned_data["durations"].split()]
        return cleaned_data


class AKSubmissionForm(AKForm):
    class Meta(AKForm.Meta):
        exclude = ['link', 'protocol_link']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add field for durations
        self.fields["durations"] = forms.CharField(
            widget=forms.Textarea,
            label=_("Duration(s)"),
            help_text=_(
                "Enter at least one planned duration (in hours). If your AK should have multiple slots, use multiple lines"),
            initial=
            self.initial.get('event').default_slot
        )

    def clean_availabilities(self):
        availabilities = super().clean_availabilities()
        # If the user did not specify availabilities assume the full event duration is possible
        if len(availabilities) == 0:
            availabilities.append(Availability.with_event_length(event=self.cleaned_data["event"]))
        return availabilities


class AKWishForm(AKForm):
    class Meta(AKForm.Meta):
        exclude = ['owners', 'link', 'protocol_link']


class AKOwnerForm(forms.ModelForm):
    required_css_class = 'required'

    class Meta:
        model = AKOwner
        fields = ['name', 'institution', 'link', 'event']
        widgets = {
            'event': forms.HiddenInput
        }


class AKDurationForm(forms.ModelForm):
    class Meta:
        model = AKSlot
        fields = ['duration', 'ak', 'event']
        widgets = {
            'ak': forms.HiddenInput,
            'event': forms.HiddenInput
        }


class AKOrgaMessageForm(forms.ModelForm):
    class Meta:
        model = AKOrgaMessage
        fields = ['ak', 'text', 'event']
        widgets = {
            'ak': forms.HiddenInput,
            'event': forms.HiddenInput,
            'text': forms.Textarea,
        }
