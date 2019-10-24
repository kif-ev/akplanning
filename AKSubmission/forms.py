from django import forms
from django.core.exceptions import ValidationError

from AKModel.models import AK, AKOwner

from django.utils.translation import ugettext_lazy as _


class AKForm(forms.ModelForm):
    class Meta:
        model = AK
        fields = ['name',
                  'short_name',
                  'link',
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
        # Use better multiple select input for owners, conflicts and prerequisites
        if "owners" in self.fields:
            self.fields["owners"].widget.attrs = {'class': 'chosen-select'}
        self.fields["conflicts"].widget.attrs = {'class': 'chosen-select'}
        self.fields["prerequisites"].widget.attrs = {'class': 'chosen-select'}

        help_tags_addition = _('Separate multiple tags with semicolon')

        # Add text fields for tags
        self.fields["tags_raw"] = forms.CharField(
            required=False,
            label=AK.tags.field.verbose_name,
            help_text=f"{AK.tags.field.help_text} ({help_tags_addition})")

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
            cleaned_data["short_name"] = ''.join(x for x in self.cleaned_data["name"].title() if x.isalnum())

        # Get tag names from raw tags
        cleaned_data["tag_names"] = [name.strip().lower() for name in cleaned_data["tags_raw"].split(";")]

        # Get durations from raw durations field
        if "durations" in cleaned_data:
            cleaned_data["durations"] = [self._clean_duration(d) for d in self.cleaned_data["durations"].split()]
        return cleaned_data


class AKSubmissionForm(AKForm):

    class Meta(AKForm.Meta):
        exclude = ['link']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add field for durations
        self.fields["durations"] = forms.CharField(
            widget=forms.Textarea,
            label=_("Duration(s)"),
            help_text=_("Enter at least one planned duration (in hours). If your AK should have multiple slots, use multiple lines")
        )


class AKEditForm(AKForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add existing tags to tag raw field
        self.fields["tags_raw"].initial = "; ".join(str(tag) for tag in self.instance.tags.all())


class AKWishForm(AKSubmissionForm):
    class Meta(AKForm.Meta):
        exclude = ['owners']


class AKOwnerForm(forms.ModelForm):
    class Meta:
        model = AKOwner
        fields = ['name', 'email', 'institution', 'link']
