import csv
import io

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
            'plan_hidden': forms.HiddenInput(),
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
        self.fields["import_categories"].queryset = self.fields["import_categories"].queryset.filter(
            event=self.initial["import_event"])
        self.fields["import_requirements"].queryset = self.fields["import_requirements"].queryset.filter(
            event=self.initial["import_event"])

        from django.apps import apps
        if apps.is_installed("AKDashboard"):
            from AKDashboard.models import DashboardButton

            self.fields["import_buttons"] = forms.ModelMultipleChoiceField(
                queryset=DashboardButton.objects.filter(event=self.initial["import_event"]),
                widget=forms.CheckboxSelectMultiple,
                label=_("Copy dashboard buttons"),
                required=False,
            )


class NewEventWizardActivateForm(forms.ModelForm):
    class Meta:
        fields = ["active"]
        model = Event


class AdminIntermediateForm(forms.Form):
    pass


class AdminIntermediateActionForm(AdminIntermediateForm):
    pks = forms.CharField(widget=forms.HiddenInput)


class SlideExportForm(AdminIntermediateForm):
    num_next = forms.IntegerField(
        min_value=0,
        max_value=6,
        initial=3,
        label=_("# next AKs"),
        help_text=_("How many next AKs should be shown on a slide?"))
    presentation_mode = forms.TypedChoiceField(
        initial=False,
        label=_("Presentation only?"),
        widget=forms.RadioSelect,
        choices=((True, _('Yes')), (False, _('No'))),
        coerce=lambda x: x == "True",
        help_text=_("Restrict AKs to those that asked for chance to be presented?"))
    wish_notes = forms.TypedChoiceField(
        initial=False,
        label=_("Space for notes in wishes?"),
        widget=forms.RadioSelect,
        choices=((True, _('Yes')), (False, _('No'))),
        coerce=lambda x: x == "True",
        help_text=_("Create symbols indicating space to note down owners and timeslots for wishes, e.g., to be filled "
                    "out on a touch screen while presenting?"))


class DefaultSlotEditorForm(AdminIntermediateForm):
    availabilities = forms.CharField(
        label=_('Default Slots'),
        help_text=_(
            'Click and drag to add default slots, double-click to delete. '
            'Or use the start and end inputs to add entries to the calendar view.'
        ),
        widget=forms.TextInput(attrs={'class': 'availabilities-editor-data'}),
        required=True,
    )


class RoomBatchCreationForm(AdminIntermediateForm):
    rooms = forms.CharField(
        label=_('New rooms'),
        help_text=_('Enter room details in CSV format. Required colum is "name", optional colums are "location", '
                    '"capacity", and "url" for online/hybrid rooms. Delimiter: Semicolon'),
        widget=forms.Textarea,
        required=True,
    )

    def clean_rooms(self):
        rooms_raw_text = self.cleaned_data["rooms"]
        rooms_raw_dict = csv.DictReader(io.StringIO(rooms_raw_text), delimiter=";")

        if "name" not in rooms_raw_dict.fieldnames:
            raise forms.ValidationError(_("CSV must contain a name column"))

        return rooms_raw_dict
