# This part of the code was adapted from pretalx (https://github.com/pretalx/pretalx)
# Copyright 2017-2019, Tobias Kunze
# Original Copyrights licensed under the Apache License, Version 2.0 http://www.apache.org/licenses/LICENSE-2.0
# Changes are marked in the code
import datetime
import json

from django import forms
from django.db import transaction
from django.db.models.signals import post_save
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext_lazy as _

from AKModel.availability.models import Availability
from AKModel.availability.serializers import AvailabilitySerializer
from AKModel.models import Event


class AvailabilitiesFormMixin(forms.Form):
    availabilities = forms.CharField(
        label=_('Availability'),
        help_text=_(
            'Click and drag to mark the availability during the event, double-click to delete. '
            'Or use the start and end inputs to add entries to the calendar view.'  # Adapted help text
        ),
        widget=forms.TextInput(attrs={'class': 'availabilities-editor-data'}),
        required=False,
    )

    def _serialize(self, event, instance):
        if instance:
            availabilities = AvailabilitySerializer(
                instance.availabilities.all(), many=True
            ).data
        else:
            availabilities = []

        return json.dumps(
            {
                'availabilities': availabilities,
                'event': {
                    # 'timezone': event.timezone,
                    'date_from': str(event.start),
                    'date_to': str(event.end),
                },
            }
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = self.initial.get('event')
        if isinstance(self.event, int):
            self.event = Event.objects.get(pk=self.event)
        initial = kwargs.pop('initial', dict())
        initial['availabilities'] = self._serialize(self.event, kwargs['instance'])
        if not isinstance(self, forms.BaseModelForm):
            kwargs.pop('instance')
        kwargs['initial'] = initial

    def _parse_availabilities_json(self, jsonavailabilities):
        try:
            rawdata = json.loads(jsonavailabilities)
        except ValueError:
            raise forms.ValidationError("Submitted availabilities are not valid json.")
        if not isinstance(rawdata, dict):
            raise forms.ValidationError(
                "Submitted json does not comply with expected format, should be object."
            )
        availabilities = rawdata.get('availabilities')
        if not isinstance(availabilities, list):
            raise forms.ValidationError(
                "Submitted json does not comply with expected format, missing or malformed availabilities field"
            )
        return availabilities

    def _parse_datetime(self, strdate):
        tz = self.event.timezone  # adapt to our event model

        obj = parse_datetime(strdate)
        if not obj:
            raise TypeError
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=tz)

        return obj

    def _validate_availability(self, rawavail):
        message = _("The submitted availability does not comply with the required format.")
        if not isinstance(rawavail, dict):
            raise forms.ValidationError(message)
        rawavail.pop('id', None)
        rawavail.pop('allDay', None)
        if not set(rawavail.keys()) == {'start', 'end'}:
            raise forms.ValidationError(message)

        try:
            rawavail['start'] = self._parse_datetime(rawavail['start'])
            rawavail['end'] = self._parse_datetime(rawavail['end'])
        except (TypeError, ValueError):
            raise forms.ValidationError(
                _("The submitted availability contains an invalid date.")
            )

        tz = self.event.timezone  # adapt to our event model

        timeframe_start = self.event.start  # adapt to our event model
        if rawavail['start'] < timeframe_start:
            rawavail['start'] = timeframe_start

        # add 1 day, not 24 hours, https://stackoverflow.com/a/25427822/2486196
        timeframe_end = self.event.end  # adapt to our event model
        timeframe_end = timeframe_end + datetime.timedelta(days=1)
        if rawavail['end'] > timeframe_end:
            # If the submitted availability ended outside the event timeframe, fix it silently
            rawavail['end'] = timeframe_end

    def clean_availabilities(self):
        data = self.cleaned_data.get('availabilities')
        required = (
                'availabilities' in self.fields and self.fields['availabilities'].required
        )
        if not data:
            if required:
                raise forms.ValidationError(_('Please fill in your availabilities!'))
            return None

        rawavailabilities = self._parse_availabilities_json(data)
        availabilities = []

        for rawavail in rawavailabilities:
            self._validate_availability(rawavail)
            availabilities.append(Availability(event_id=self.event.id, **rawavail))
        if not availabilities and required:
            raise forms.ValidationError(_('Please fill in your availabilities!'))
        return availabilities

    def _set_foreignkeys(self, instance, availabilities):
        """Set the reference to `instance` in each given availability.
        For example, set the availabilitiy.room_id to instance.id, in
        case instance of type Room.
        """
        reference_name = instance.availabilities.field.name + '_id'

        for avail in availabilities:
            setattr(avail, reference_name, instance.id)

    def _replace_availabilities(self, instance, availabilities: [Availability]):
        with transaction.atomic():
            # TODO: do not recreate objects unnecessarily, give the client the IDs, so we can track modifications and leave unchanged objects alone
            instance.availabilities.all().delete()
            Availability.objects.bulk_create(availabilities)
            # Trigger post save signal manually to make sure constraints are updated accordingly
            # Doing this one time is sufficient, since this will nevertheless update all availability constraint
            # violations of the corresponding AK
            if len(availabilities) > 0:
                post_save.send(Availability, instance=availabilities[0], created=True)

    def save(self, *args, **kwargs):
        instance = super().save(*args, **kwargs)
        availabilities = self.cleaned_data.get('availabilities')

        if availabilities is not None:
            self._set_foreignkeys(instance, availabilities)
            self._replace_availabilities(instance, availabilities)

        return instance  # adapt to our forms
