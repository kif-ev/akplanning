from rest_framework import serializers

from AKModel.models import AK, Room, AKSlot, AKTrack, AKCategory, AKOwner


class AKOwnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = AKOwner
        fields = '__all__'


class AKCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = AKCategory
        fields = '__all__'


class AKTrackSerializer(serializers.ModelSerializer):
    class Meta:
        model = AKTrack
        fields = '__all__'


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
