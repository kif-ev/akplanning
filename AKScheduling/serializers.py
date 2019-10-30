from rest_framework import serializers

from AKModel.models import AK, Room, AKSlot


class AKSerializer(serializers.ModelSerializer):
    class Meta:
        model = AK
        fields = '__all__'


class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = '__all__'


class AKSlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = AKSlot
        fields = '__all__'
