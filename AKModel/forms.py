"""
Central and admin forms
"""

from django import forms
from django.core.exceptions import ValidationError
from django.forms.utils import ErrorList
from django.utils.translation import gettext_lazy as _

from AKModel.availability.forms import AvailabilitiesFormMixin
from AKModel.models import AK, AKCategory, AKRequirement, AKTrack, AKType, DefaultSlot, Event, Room
from AKModel.room_import import decode_csv_bytes


class DateTimeInput(forms.DateTimeInput):
    """
    Simple widget for datetime input fields using the HTML5 datetime-local input type

    This uses the browser's native date picker instead of a JS library
    (loading such libraries from a CDN is blocked by the content security policy).
    """
    input_type = 'datetime-local'

    def __init__(self, attrs=None, **kwargs):
        # datetime-local inputs only accept initial values in ISO format (without seconds and timezone)
        kwargs.setdefault("format", "%Y-%m-%dT%H:%M")
        super().__init__(attrs, **kwargs)


class TimespanWidget(forms.MultiWidget):
    """
    Widget to input a timespan as two datetime pickers (start and end) displayed in one row
    """
    template_name = "AKModel/widgets/timespan.html"

    def __init__(self, attrs=None):
        widgets = [
            DateTimeInput(attrs={"aria-label": _("Timespan start")}),
            DateTimeInput(attrs={"aria-label": _("Timespan end")}),
        ]
        super().__init__(widgets, attrs)

    def decompress(self, value):
        # The compressed value is a (start, end) tuple, see TimespanField
        return list(value) if value else [None, None]


class TimespanField(forms.MultiValueField):
    """
    Form field for an optional timespan, consisting of a start and an end datetime

    The cleaned value is a (start, end) tuple. Both parts may be None if they were left empty.
    """
    widget = TimespanWidget

    def __init__(self, **kwargs):
        fields = (forms.DateTimeField(required=False), forms.DateTimeField(required=False))
        super().__init__(fields=fields, require_all_fields=False, **kwargs)

    def prepare_value(self, value):
        # Let the datetime subfields prepare their values,
        # this converts timezone-aware datetimes to the current timezone for display
        if isinstance(value, (list, tuple)):
            return [field.prepare_value(v) for field, v in zip(self.fields, value)]
        return value

    def compress(self, data_list):
        # All parts empty: no timespan given
        if not data_list:
            return None, None
        start, end = data_list
        if start and end and start >= end:
            raise ValidationError(_("The end of the timespan must be after its start"), code="invalid_timespan")
        return start, end


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
        fields = ['name', 'slug', 'timezone', 'plan_hidden', 'poll_hidden']
        widgets = {
            'plan_hidden': forms.HiddenInput(),
            'poll_hidden': forms.HiddenInput(),
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
        exclude = ['plan_published_at', 'poll_published_at']
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
            'poll_hidden': forms.HiddenInput(),
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


class CVMarkResolvedForm(AdminIntermediateActionForm):
    """
    Form for marking constraint violations as manually resolved, allows to (optionally) specify a reason for that
    """
    resolution_reason = forms.CharField(
            label=_('Resolution Reason'),
            help_text=_('Why are these violations resolved or acceptable? (optional)'),
            required=False,
            widget=forms.Textarea(attrs={'rows': 3}),
    )


class SlideExportForm(AdminIntermediateForm):
    """
    Form to control the slides generated from the AK list of an event

    The user can select how many upcoming AKs are displayed at the footer to inform people that it is their turn soon,
    whether the AK list should be restricted to those AKs that where marked for presentation, and whether ther should
    be a symbol and empty space to take notes on for wishes.
    Additionally, the slides can be restricted to AKs that have at least one slot in a given timespan.
    The initial values of this timespan (start and end of the event) are set by the view.
    """
    num_next = forms.IntegerField(
            min_value=0,
            max_value=6,
            initial=3,
            label=_("# next AKs"),
            help_text=_("How many next AKs should be shown on a slide?"))
    categories = forms.MultipleChoiceField(
            label=_("AK Categories"),
            help_text=_("Which categories should be included in the slides?"),
            widget=forms.CheckboxSelectMultiple,
            choices=[],
            required=False)
    types = forms.MultipleChoiceField(
            label=_("AK Types"),
            help_text=_("Which AK types should be included in the slides?"),
            widget=forms.CheckboxSelectMultiple,
            choices=[],
            required=False)
    types_all_selected_only = forms.BooleanField(
            initial=False,
            label=_("Only show AKs with all selected types?"),
            help_text=_("If checked, only AKs that have all selected types will be shown in the slides. "
                        "If unchecked, AKs with at least one of the selected types will be shown."),
            required=False)
    timespan = TimespanField(
            label=_("Timespan"),
            help_text=_("Only include AKs with at least one slot overlapping this timespan. "
                        "Default: Whole event, then also unscheduled slots are shown."),
            required=False)
    presentation_mode = forms.TypedChoiceField(
            initial=False,
            label=_("Presentation only?"),
            widget=forms.RadioSelect,
            choices=((True, _('Yes')), (False, _('No'))),
            coerce=lambda x: x == "True",
            help_text=_("Restrict AKs to those that asked for chance to be presented?"))


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
    rooms. Makes sure exactly one input (file or text) is used and provides the decoded data as ``csv_text``,
    the detailed validation of the content happens in :func:`AKModel.room_import.parse_rooms_csv`.
    """
    create_default_availabilities = forms.BooleanField(
            label=_('Default availabilities?'),
            help_text=_('Create default availabilities for all rooms?'),
            required=False
    )
    csv_data = forms.CharField(
            label=_('New rooms'),
            help_text=_('Enter room details in CSV format. Required column is "name", optional columns are "location", '
                        '"capacity", "url" for online/hybrid rooms. Optionally one column per requirement, column name '
                        'should be requirement name, if requirement should be set, value should be "x". '
                        'Delimiter: Semicolon'),
            widget=forms.Textarea,
            required=False,
    )
    csv_file = forms.FileField(
            required=False,
            label=_("File with csv data"),
            help_text=_("File with csv data for room creation"),
    )

    def clean(self):
        """
        Make sure exactly one kind of input was used and provide its (decoded) content as ``csv_text``

        :return: cleaned data
        :rtype: dict
        """
        cleaned_data = super().clean()
        if cleaned_data.get("csv_file") and cleaned_data.get("csv_data"):
            err = ValidationError(
                    _("Please enter data as a file OR via text, not both."), "invalid"
            )
            self.add_error("csv_data", err)
            self.add_error("csv_file", err)

        elif not (cleaned_data.get("csv_file") or cleaned_data.get("csv_data")):
            err = ValidationError(
                    _("No data entered. Please enter data as a file or via text."),
                    "invalid",
            )
            self.add_error("csv_data", err)
            self.add_error("csv_file", err)

        elif cleaned_data.get("csv_file"):
            with cleaned_data["csv_file"].open() as csv_file:
                cleaned_data["csv_text"] = decode_csv_bytes(csv_file.read())
        else:
            cleaned_data["csv_text"] = cleaned_data["csv_data"]

        return cleaned_data


class RoomBatchImportConfirmForm(AdminIntermediateForm):
    """
    Form to confirm a room batch import after its preview was shown,
    holds the data entered in :class:`RoomBatchCreationForm`
    """
    csv_data = forms.CharField(widget=forms.HiddenInput, strip=False)
    create_default_availabilities = forms.BooleanField(widget=forms.HiddenInput, required=False)


class ShiftByOffsetForm(AdminIntermediateActionForm):
    """
    Form to specify an offset (in hours) that the given entities will be shifted by
    """
    offset_hours = forms.FloatField(
            label=_("Offset (hours)"),
            help_text=_("Specify the offset in hours by which the selected entities should be shifted.")
    )


class TrackAssignmentForm(AdminIntermediateActionForm):
    """
    Form to assign AKs to a given track
    """
    track = forms.ModelChoiceField(
            queryset=None,
            label=_("Existing track"),
            help_text=_("Select the track to assign the selected AKs to."),
            required=False,
    )
    new_track = forms.CharField(
            label=_("New track"),
            help_text=_('Alternatively, enter a new track name'),
            required=False,
    )

    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event')
        super().__init__(*args, **kwargs)
        self.fields['track'].queryset = AKTrack.objects.filter(event=event).all()

    def clean(self):
        cleaned_data = super().clean()

        # Check whether the AKs with the given PKs are from different events
        aks = AK.objects.filter(pk__in=self.cleaned_data['pks'].split(','))
        events = set(ak.event for ak in aks)
        if len(events) > 1:
            err = ValidationError(
                    _("Selected AKs belong to different events. Please select only AKs from the same event."),
                    "invalid",
            )
            self.add_error(None, err)
            return cleaned_data
        event = AK.objects.get(pk=self.cleaned_data['pks'][0]).event

        # Neither existing nor new track
        if not (cleaned_data.get("track") or cleaned_data.get("new_track")):
            err = ValidationError(
                    _("No track selected. Please choose an existing track or specify the name of a new one."),
                    "invalid",
            )
            self.add_error("track", err)
            self.add_error("new_track", err)

        # Existing and new track at the same time
        elif cleaned_data.get("track") and cleaned_data.get("new_track"):
            err = ValidationError(
                    _("Please choose either an existing track or specify the name of a new one, not both."),
                    "invalid",
            )
            self.add_error("track", err)
            self.add_error("new_track", err)

        # Check whether track with this name already exists
        elif cleaned_data.get("new_track"):
            new_track_name = cleaned_data["new_track"]
            if event.aktrack_set.filter(event=event, name=new_track_name).exists():
                err = ValidationError(
                        _("A track with this name already exists. Please choose a different name."),
                        "invalid",
                )
                self.add_error("new_track", err)

        return cleaned_data


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


class DefaultSlotCategoriesForm(AdminIntermediateActionForm):
    """
    Form to assign categories to default slots in bulk
    """
    primary_categories = forms.ModelMultipleChoiceField(
            queryset=None,
            label=_("Primary categories"),
            help_text=_("Categories that should be assigned to these slots primarily"),
            required=False,
            widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event')
        super().__init__(*args, **kwargs)
        self.fields['primary_categories'].queryset = AKCategory.objects.filter(event=event).all()

    def clean(self):
        cleaned_data = super().clean()

        # Check whether the default slots with the given PKs are from different events
        slots = (DefaultSlot.objects.filter(pk__in=self.cleaned_data['pks'].split(',')))
        events = set(slot.event for slot in slots)
        if len(events) > 1:
            err = ValidationError(
                    _("Selected default slots belong to different events. Please select only default slots from the same event."),
                    "invalid",
            )
            self.add_error(None, err)
            return cleaned_data
        event = slots[0].event

        return cleaned_data
