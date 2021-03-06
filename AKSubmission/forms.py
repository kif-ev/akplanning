import itertools
import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _

from AKModel.availability.forms import AvailabilitiesFormMixin
from AKModel.models import AK, AKOwner, AKCategory, AKRequirement, AKSlot, AKOrgaMessage


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

        help_tags_addition = _('Separate multiple tags with comma or semicolon')

        # Add text fields for tags
        self.fields["tags_raw"] = forms.CharField(
            required=False,
            label=AK.tags.field.verbose_name,
            help_text=f"{AK.tags.field.help_text} ({help_tags_addition})")

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

        # Get tag names from raw tags
        cleaned_data["tag_names"] = [name.strip().lower() for name
                                     in self.split_string.split(cleaned_data["tags_raw"])
                                     if name.strip() != '']

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


class AKEditForm(AKForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add existing tags to tag raw field
        self.fields["tags_raw"].initial = "; ".join(str(tag) for tag in self.instance.tags.all())


class AKWishForm(AKSubmissionForm):
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial = {**self.initial, **kwargs['initial']}
        event = self.initial.get('event')
        if event is not None:
            self.initial['duration'] = event.default_slot


class AKOrgaMessageForm(forms.ModelForm):
    class Meta:
        model = AKOrgaMessage
        fields = ['ak', 'text']
        widgets = {
            'ak': forms.HiddenInput,
            'text': forms.Textarea,
        }
