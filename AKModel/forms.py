"""
Central and admin forms
"""

import csv
import io

from django import forms
from django.forms.utils import ErrorList
from django.utils.translation import gettext_lazy as _

from AKModel.availability.forms import AvailabilitiesFormMixin
from AKModel.models import Event, AKCategory, AKRequirement, Room, AKType


class DateTimeInput(forms.DateInput):
    """
    Simple widget for datetime input fields using the HTML5 datetime-local input type
    """
    input_type = 'datetime-local'


class NewEventWizardStartForm(forms.ModelForm):
    """
    Initial view of new event wizard

    This form is a model form for Event, but only with a subset of the required fields.
    It is therefore not possible to really create an event using this form, but only to enter
    information, in particular the timezone, that is needed to correctly handle/parse the user
    inputs for further required fields like start and end of the event.

    The form will be used for this partial input, the input of the remaining required fields
    will then be handled by :class:`NewEventWizardSettingsForm` (see below).
    """
    class Meta:
        model = Event
        fields = ['name', 'slug', 'timezone', 'plan_hidden']
        widgets = {
            'plan_hidden': forms.HiddenInput(),
        }

    # Special hidden field for wizard state handling
    is_init = forms.BooleanField(initial=True, widget=forms.HiddenInput)


class NewEventWizardSettingsForm(forms.ModelForm):
    """
    Form for second view of the event creation wizard.

    Will handle the input of the remaining required as well as some optional fields.
    See also :class:`NewEventWizardStartForm`.
    """
    class Meta:
        model = Event
        fields = "__all__"
        exclude = ['plan_published_at']
        widgets = {
            'name': forms.HiddenInput(),
            'slug': forms.HiddenInput(),
            'timezone': forms.HiddenInput(),
            'active': forms.HiddenInput(),
            'start': DateTimeInput(),
            'end': DateTimeInput(),
            'interest_start': DateTimeInput(),
            'interest_end': DateTimeInput(),
            'reso_deadline': DateTimeInput(),
            'plan_hidden': forms.HiddenInput(),
        }


class NewEventWizardPrepareImportForm(forms.Form):
    """
    Wizard form for choosing an event to import/copy elements (requirements, categories, etc) from.
    Is used to restrict the list of elements to choose from in the next step (see :class:`NewEventWizardImportForm`).
    """
    import_event = forms.ModelChoiceField(
        queryset=Event.objects.all(),
        label=_("Copy ak requirements and ak categories of existing event"),
        help_text=_("You can choose what to copy in the next step")
    )


class NewEventWizardImportForm(forms.Form):
    """
    Wizard form for excaclty choosing which elemments to copy/import for the newly created event.
    Possible elements are categories, requirements, and dashboard buttons if AKDashboard is active.
    The lists are restricted to elements from the event selected in the previous step
    (see :class:`NewEventWizardPrepareImportForm`).
    """
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

    import_types = forms.ModelMultipleChoiceField(
        queryset=AKType.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label=_("Copy types"),
        required=False,
    )

    # pylint: disable=too-many-arguments
    def __init__(self, data=None, files=None, auto_id='id_%s', prefix=None, initial=None, error_class=ErrorList,
                 label_suffix=None, empty_permitted=False, field_order=None, use_required_attribute=None,
                 renderer=None):
        super().__init__(data, files, auto_id, prefix, initial, error_class, label_suffix, empty_permitted, field_order,
                         use_required_attribute, renderer)
        self.fields["import_categories"].queryset = self.fields["import_categories"].queryset.filter(
            event=self.initial["import_event"])
        self.fields["import_requirements"].queryset = self.fields["import_requirements"].queryset.filter(
            event=self.initial["import_event"])
        self.fields["import_types"].queryset = self.fields["import_types"].queryset.filter(
            event=self.initial["import_event"])

        # pylint: disable=import-outside-toplevel
        # Local imports used to prevent cyclic imports and to only import when AKDashboard is available
        from django.apps import apps
        if apps.is_installed("AKDashboard"):
            # If AKDashboard is active, allow to copy dashboard buttons, too
            from AKDashboard.models import DashboardButton
            self.fields["import_buttons"] = forms.ModelMultipleChoiceField(
                queryset=DashboardButton.objects.filter(event=self.initial["import_event"]),
                widget=forms.CheckboxSelectMultiple,
                label=_("Copy dashboard buttons"),
                required=False,
            )


class NewEventWizardActivateForm(forms.ModelForm):
    """
    Wizard form to activate the newly created event
    """
    class Meta:
        fields = ["active"]
        model = Event


class AdminIntermediateForm(forms.Form):
    """
    Base form for admin intermediate views (forms used there should inherit from this,
    by default, the form is empty since it is only needed for the confirmation button)
    """


class AdminIntermediateActionForm(AdminIntermediateForm):
    """
    Form for Admin Action Confirmation views -- has a pks field needed to handle the serialization/deserialization of
    the IDs of the entities the user selected for the admin action to be performed on
    """
    pks = forms.CharField(widget=forms.HiddenInput)


class SlideExportForm(AdminIntermediateForm):
    """
    Form to control the slides generated from the AK list of an event

    The user can select how many upcoming AKs are displayed at the footer to inform people that it is their turn soon,
    whether the AK list should be restricted to those AKs that where marked for presentation, and whether ther should
    be a symbol and empty space to take notes on for wishes
    """
    num_next = forms.IntegerField(
        min_value=0,
        max_value=6,
        initial=3,
        label=_("# next AKs"),
        help_text=_("How many next AKs should be shown on a slide?"))
    types = forms.MultipleChoiceField(
        label=_("AK Types"),
        help_text=_("Which AK types should be included in the slides?"),
        widget=forms.CheckboxSelectMultiple,
        choices=[],
        required=False)
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
    """
    Form for default slot editor
    """
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
    """
    Form for room batch creation

    Allows to input a list of room details and choose whether default availabilities should be generated for these
    rooms. Will check that the input follows a CSV format with at least a name column present.
    """
    rooms = forms.CharField(
        label=_('New rooms'),
        help_text=_('Enter room details in CSV format. Required colum is "name", optional colums are "location", '
                    '"capacity", and "url" for online/hybrid rooms. Delimiter: Semicolon'),
        widget=forms.Textarea,
        required=True,
    )
    create_default_availabilities = forms.BooleanField(
        label=_('Default availabilities?'),
        help_text=_('Create default availabilities for all rooms?'),
        required=False
    )

    def clean_rooms(self):
        """
        Validate and transform the input for the rooms textfield
        Treat the input as CSV and turn it into a dict containing the relevant information.

        :return: a dict containing the raw room information
        :rtype: dict[str, str]
        """
        rooms_raw_text = self.cleaned_data["rooms"]
        rooms_raw_dict = csv.DictReader(io.StringIO(rooms_raw_text), delimiter=";")

        if "name" not in rooms_raw_dict.fieldnames:
            raise forms.ValidationError(_("CSV must contain a name column"))

        return rooms_raw_dict


class RoomForm(forms.ModelForm):
    """
    Room (creation) form (basic), will be extended for handling of availabilities
    (see :class:`RoomFormWithAvailabilities`) and also for creating hybrid rooms in AKOnline (if active)
    """
    class Meta:
        model = Room
        fields = ['name',
                  'location',
                  'capacity',
                  'event',
                  ]


class RoomFormWithAvailabilities(AvailabilitiesFormMixin, RoomForm):
    """
    Room (update) form including handling of availabilities, extends :class:`RoomForm`
    """
    class Meta:
        model = Room
        fields = ['name',
                  'location',
                  'capacity',
                  'properties',
                  'event',
                  ]

        widgets = {
            'properties': forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        # Init availability mixin
        kwargs['initial'] = {}
        super().__init__(*args, **kwargs)
        self.initial = {**self.initial, **kwargs['initial']}
        # Filter possible values for m2m when event is specified
        if hasattr(self.instance, "event") and self.instance.event is not None:
            self.fields["properties"].queryset = AKRequirement.objects.filter(event=self.instance.event)
