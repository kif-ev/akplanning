from rest_framework import serializers

from AKModel.models import AK, AKCategory, AKOwner, AKSlot, AKTrack, Room


class StringListField(serializers.ListField):
    """List field containing strings."""

    child = serializers.CharField()


class IntListField(serializers.ListField):
    """List field containing integers."""

    child = serializers.IntegerField()


class AKOwnerSerializer(serializers.ModelSerializer):
    """
    REST Framework Serializer for AKOwner
    """
    class Meta:
        model = AKOwner
        fields = '__all__'


class AKCategorySerializer(serializers.ModelSerializer):
    """
    REST Framework Serializer for AKCategory
    """
    class Meta:
        model = AKCategory
        fields = '__all__'


class AKTrackSerializer(serializers.ModelSerializer):
    """
    REST Framework Serializer for AKTrack
    """
    class Meta:
        model = AKTrack
        fields = '__all__'


class AKSerializer(serializers.ModelSerializer):
    """
    REST Framework Serializer for AK
    """
    class Meta:
        model = AK
        fields = '__all__'


class RoomSerializer(serializers.ModelSerializer):
    """
    REST Framework Serializer for Room
    """
    class Meta:
        model = Room
        fields = '__all__'


class AKSlotSerializer(serializers.ModelSerializer):
    """
    REST Framework Serializer for AKSlot
    """
    class Meta:
        model = AKSlot
        fields = '__all__'

    treat_as_local = serializers.BooleanField(required=False, default=False, write_only=True)

    def create(self, validated_data:dict):
        # Handle timezone adaption based upon the control field "treat_as_local":
        # If it is set, ignore timezone submitted from the browser (will always be UTC)
        # and treat it as input in the events timezone instead
        if validated_data['treat_as_local']:
            validated_data['start'] = validated_data['start'].replace(tzinfo=None).astimezone(
                validated_data['event'].timezone)
        del validated_data['treat_as_local']
        return super().create(validated_data)
