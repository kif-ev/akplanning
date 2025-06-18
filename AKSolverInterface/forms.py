import json

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from jsonschema.exceptions import best_match

from AKModel.forms import AdminIntermediateForm
from AKModel.models import AKCategory, AKTrack, AKType, Event
from AKSolverInterface.utils import construct_schema_validator


class JSONExportControlForm(forms.Form):
    """Form to control what objects are exported to the solver."""

    # TODO: Filter rooms out by property?
    # TODO: Add room availability filter?

    export_scheduled_aks_as_fixed = forms.BooleanField(
        label=_("Fixate all scheduled slots for the solver"),
        help_text=_(
            "In the solver export, all assigned times and room to slots are handled "
            "as if the slot were fixed."
        ),
        required=False,
    )
    export_categories = forms.ModelMultipleChoiceField(
        queryset=AKCategory.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label=_("AK Categories to include in the export"),
        required=False,
    )
    export_tracks = forms.ModelMultipleChoiceField(
        queryset=AKTrack.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label=_("AK tracks to include in the export"),
        required=False,
    )
    export_types = forms.ModelMultipleChoiceField(
        queryset=AKType.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label=_("AK types to include in the export"),
        required=False,
    )

    field_order = [
        "export_scheduled_aks_as_fixed",
        "export_categories",
        "export_tracks",
        "export_types",
    ]

    def __init__(self, *args, event: Event, **kwargs):
        self.event = event
        initial = kwargs.get("initial", {})
        initial["event"] = event
        kwargs["initial"] = initial

        super().__init__(*args, **kwargs)
        def _set_queryset(field_name: str):
            # restrict queryset to all objects of this event
            self.fields[field_name].queryset = self.fields[field_name].queryset.filter(
                event=self.event,
            )

            # default init: all objects are checked
            self.fields[field_name].initial = self.fields[field_name].queryset

            # if queryset is empty, simply remove the field
            if not self.fields[field_name].queryset.exists():
                self.fields.pop(field_name)

        for field_name in ["export_categories", "export_tracks", "export_types"]:
            _set_queryset(field_name)


class JSONScheduleImportForm(AdminIntermediateForm):
    """Form to import an AK schedule from a json file."""

    json_data = forms.CharField(
        required=False,
        widget=forms.Textarea,
        label=_("JSON data"),
        help_text=_("JSON data from the scheduling solver"),
    )

    json_file = forms.FileField(
        required=False,
        label=_("File with JSON data"),
        help_text=_("File with JSON data from the scheduling solver"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.json_schema_validator = construct_schema_validator(
            schema="solver-output.schema.json"
        )

    def _check_json_data(self, data: str):
        """Validate `data` against our JSON schema.

        :param data: The JSON string to validate using `self.json_schema_validator`.
        :type data: str
        :raises ValidationError: if the validation fails, with a description of the cause.
        :return: The parsed JSON dict, if validation is successful.
        """
        try:
            schedule = json.loads(data)
        except json.JSONDecodeError as ex:
            raise ValidationError(_("Cannot decode as JSON"), "invalid") from ex

        error = best_match(self.json_schema_validator.iter_errors(schedule))
        if error:
            raise ValidationError(
                _("Invalid JSON format: %(msg)s at %(error_path)s"),
                "invalid",
                params={"msg": error.message, "error_path": error.json_path},
            ) from error

        return schedule

    def clean(self):
        """Extract and validate entered JSON data.

        We allow entering of the schedule from two sources:
        1. from an uploaded file
        2. from a text field.

        This function checks that data is entered from exactly one source.
        If so, the entered JSON string is validated against our schema.
        Any errors are reported at the corresponding form field.
        """
        cleaned_data = super().clean()
        if cleaned_data.get("json_file") and cleaned_data.get("json_data"):
            err = ValidationError(
                _("Please enter data as a file OR via text, not both."), "invalid"
            )
            self.add_error("json_data", err)
            self.add_error("json_file", err)
        elif not (cleaned_data.get("json_file") or cleaned_data.get("json_data")):
            err = ValidationError(
                _("No data entered. Please enter data as a file or via text."),
                "invalid",
            )
            self.add_error("json_data", err)
            self.add_error("json_file", err)
        else:
            source_field = "json_data"
            data = cleaned_data.get(source_field)
            if not data:
                source_field = "json_file"
                with cleaned_data.get(source_field).open() as ff:
                    data = ff.read()
            try:
                cleaned_data["data"] = self._check_json_data(data)
            except ValidationError as ex:
                self.add_error(source_field, ex)
        return cleaned_data
