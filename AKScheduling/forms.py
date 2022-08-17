from django import forms

from AKModel.models import AK


class AKInterestForm(forms.ModelForm):
    required_css_class = 'required'

    class Meta:
        model = AK
        fields = ['interest',
                  'notes',
                  ]
