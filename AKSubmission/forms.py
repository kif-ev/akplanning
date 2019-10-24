from django import forms

from AKModel.models import AK, AKOwner


class AKForm(forms.ModelForm):
    class Meta:
        model = AK
        fields = ['name',
                  'short_name',
                  'link',
                  'owners',
                  'description',
                  'category',
                  'tags',
                  'reso',
                  'present',
                  'requirements',
                  'conflicts',
                  'prerequisites',
                  'notes',
                  ]

        widgets = {
            'requirements': forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Use better multiple select input for owners, conflicts and prerequisites
        self.fields["owners"].widget.attrs = {'class': 'chosen-select'}
        self.fields["conflicts"].widget.attrs = {'class': 'chosen-select'}
        self.fields["prerequisites"].widget.attrs = {'class': 'chosen-select'}


class AKWishForm(AKForm):
    class Meta(AKForm.Meta):
        exclude = ['owners']


class AKOwnerForm(forms.ModelForm):
    class Meta:
        model = AKOwner
        fields = ['name', 'email', 'institution', 'link']
