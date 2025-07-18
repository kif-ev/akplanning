# This part of the code was adapted from pretalx (https://github.com/pretalx/pretalx)
# Copyright 2017-2019, Tobias Kunze
# Original Copyrights licensed under the Apache License, Version 2.0 http://www.apache.org/licenses/LICENSE-2.0
# Documentation was mainly added by us, other changes are marked in the code
from django.utils import timezone
from rest_framework.fields import SerializerMethodField
from rest_framework.serializers import BaseSerializer, ModelSerializer

from AKModel.availability.models import Availability
from AKModel.models import Event


class AvailabilitySerializer(ModelSerializer):
    """
    REST Framework Serializer for Availability
    """
    allDay = SerializerMethodField()
    start = SerializerMethodField()
    end = SerializerMethodField()

    def get_allDay(self, obj):  # pylint: disable=invalid-name
        """
        Bridge between naming conventions of python and fullcalendar by providing the all_day field as allDay, too
        """
        return obj.all_day

    def get_start(self, obj):
        """
        Get start timestamp

        Use already localized strings in serialized field
        (default would be UTC, but that would require heavy timezone calculation on client side)
        """
        return timezone.localtime(obj.start, obj.event.timezone).strftime("%Y-%m-%dT%H:%M:%S")

    def get_end(self, obj):
        """
        Get end timestamp

        Use already localized strings in serialized field
        (default would be UTC, but that would require heavy timezone calculation on client side)
        """
        return timezone.localtime(obj.end, obj.event.timezone).strftime("%Y-%m-%dT%H:%M:%S")

    class Meta:
        model = Availability
        fields = ('id', 'start', 'end', 'allDay')


class AvailabilityFormSerializer(BaseSerializer):
    """Serializer to configure an availability form."""

    def create(self, validated_data):
        raise ValueError("`AvailabilityFormSerializer` is read-only.")

    def to_internal_value(self, data):
        raise ValueError("`AvailabilityFormSerializer` is read-only.")

    def update(self, instance, validated_data):
        raise ValueError("`AvailabilityFormSerializer` is read-only.")

    def to_representation(self, instance: tuple[Availability, Event], **kwargs):
        availabilities, event = instance

        return {
            'availabilities': AvailabilitySerializer(availabilities, many=True).data,
            'event': {
                # 'timezone': event.timezone,
                'date_from': str(event.start),
                'date_to': str(event.end),
            },
        }
