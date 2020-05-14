# This part of the code was adapted from pretalx (https://github.com/pretalx/pretalx)
# Copyright 2017-2019, Tobias Kunze
# Original Copyrights licensed under the Apache License, Version 2.0 http://www.apache.org/licenses/LICENSE-2.0
# Changes are marked in the code
from rest_framework.fields import SerializerMethodField
from rest_framework.serializers import ModelSerializer

from AKModel.availability.models import Availability


class AvailabilitySerializer(ModelSerializer):
    allDay = SerializerMethodField()

    def get_allDay(self, obj):
        return obj.all_day

    class Meta:
        model = Availability
        fields = ('id', 'start', 'end', 'allDay')
