from django import forms
from django.utils.translation import gettext_lazy as _

from AKModel.models import AK


class AKInterestForm(forms.ModelForm):
    """
    Form for quickly changing the interest count and notes of an AK
    """
    required_css_class = 'required'

    class Meta:
        model = AK
        fields = ['interest',
                  'notes',
                  ]


class AKAddSlotForm(forms.Form):
    """
    Form to create a new slot for an existing AK directly from scheduling view
    """
    start = forms.CharField(label=_("Start"), disabled=True)
    end = forms.CharField(label=_("End"), disabled=True)
    duration = forms.CharField(label=_("Duration"), disabled=True)
    room = forms.IntegerField(label=_("Room"), disabled=True)

    def __init__(self, event):
        super().__init__()
        self.fields['ak'] = forms.ModelChoiceField(event.ak_set.all(), label=_("AK"))
