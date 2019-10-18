from django import forms

from AKModel.models import AK


class AKForm(forms.ModelForm):
    class Meta:
        model = AK
        fields = '__all__'
