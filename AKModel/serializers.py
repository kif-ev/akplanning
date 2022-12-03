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

    treat_as_local = serializers.BooleanField(required=False, default=False, write_only=True)

    def create(self, validated_data:dict):
        if validated_data['treat_as_local']:
            validated_data['start'] = validated_data['start'].replace(tzinfo=None).astimezone(
                validated_data['event'].timezone)
        del validated_data['treat_as_local']
        return super().create(validated_data)
