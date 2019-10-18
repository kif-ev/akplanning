from django import forms

from AKModel.models import AK


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
                  'event']
