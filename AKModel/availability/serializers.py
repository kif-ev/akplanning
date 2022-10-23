# This part of the code was adapted from pretalx (https://github.com/pretalx/pretalx)
# Copyright 2017-2019, Tobias Kunze
# Original Copyrights licensed under the Apache License, Version 2.0 http://www.apache.org/licenses/LICENSE-2.0
# Changes are marked in the code
from django.utils import timezone
from rest_framework.fields import SerializerMethodField
from rest_framework.serializers import ModelSerializer

from AKModel.availability.models import Availability


class AvailabilitySerializer(ModelSerializer):
    allDay = SerializerMethodField()
    start = SerializerMethodField()
    end = SerializerMethodField()

    def get_allDay(self, obj):
        return obj.all_day

    # Use already localized strings in serialized field
    # (default would be UTC, but that would require heavy timezone calculation on client side)
    def get_start(self, obj):
        return timezone.localtime(obj.start, obj.event.timezone).strftime("%Y-%m-%dT%H:%M:%S")

    def get_end(self, obj):
        return timezone.localtime(obj.end, obj.event.timezone).strftime("%Y-%m-%dT%H:%M:%S")

    class Meta:
        model = Availability
        fields = ('id', 'start', 'end', 'allDay')
