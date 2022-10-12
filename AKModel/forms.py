from bootstrap_datepicker_plus import DateTimePickerInput
from django import forms
from django.forms.utils import ErrorList
from django.utils.translation import gettext_lazy as _

from AKModel.models import Event, AKCategory, AKRequirement


class NewEventWizardStartForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['name', 'slug', 'timezone', 'plan_hidden']
        widgets = {
            'plan_hidden': forms.HiddenInput(),
        }

    is_init = forms.BooleanField(initial=True, widget=forms.HiddenInput)


class NewEventWizardSettingsForm(forms.ModelForm):
    class Meta:
        model = Event
        exclude = []
        widgets = {
            'name': forms.HiddenInput(),
            'slug': forms.HiddenInput(),
            'timezone': forms.HiddenInput(),
            'active': forms.HiddenInput(),
            'start': DateTimePickerInput(options={"format": "YYYY-MM-DD HH:mm"}),
            'end': DateTimePickerInput(options={"format": "YYYY-MM-DD HH:mm"}),
            'reso_deadline': DateTimePickerInput(options={"format": "YYYY-MM-DD HH:mm"}),
        }


class NewEventWizardPrepareImportForm(forms.Form):
    import_event = forms.ModelChoiceField(
        queryset=Event.objects.all(),
        label=_("Copy ak requirements and ak categories of existing event"),
        help_text=_("You can choose what to copy in the next step")
    )


class NewEventWizardImportForm(forms.Form):
    import_categories = forms.ModelMultipleChoiceField(
        queryset=AKCategory.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label=_("Copy ak categories"),
        required=False,
    )

    import_requirements = forms.ModelMultipleChoiceField(
        queryset=AKRequirement.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label=_("Copy ak requirements"),
        required=False,
    )

    def __init__(self, data=None, files=None, auto_id='id_%s', prefix=None, initial=None, error_class=ErrorList,
                 label_suffix=None, empty_permitted=False, field_order=None, use_required_attribute=None,
                 renderer=None):
        super().__init__(data, files, auto_id, prefix, initial, error_class, label_suffix, empty_permitted, field_order,
                         use_required_attribute, renderer)
        self.fields["import_categories"].queryset = self.fields["import_categories"].queryset.filter(event=self.initial["import_event"])
        self.fields["import_requirements"].queryset = self.fields["import_requirements"].queryset.filter(event=self.initial["import_event"])


class NewEventWizardActivateForm(forms.ModelForm):
    class Meta:
        fields = ["active"]
        model = Event
