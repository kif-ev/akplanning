from rest_framework import serializers

from AKModel.models import AKSlot
from AKModel.serializers import StringListField
from AKPreference.models import AKPreference, EventParticipant

class ExportAKPreferenceSerializer(serializers.ModelSerializer):
    """Export serializer for AKPreference objects.

    Used to serialize AKPreference objects for the export to a solver.
    Part of the implementation of the format of the KoMa solver:
    https://github.com/Die-KoMa/ak-plan-optimierung/wiki/Input-&-output-format#input--output-format
    """

    class Meta:
        model = AKPreference
        fields = ["required", "preference_score"]
        read_only_fields = ["required", "preference_score"]


class ExportAKPreferencePerSlotSerializer(serializers.BaseSerializer):
    """Export serializer to associate AKPreferences with the AK's AKSlot objects.

    The AKPreference model stores the preference per AK object.
    The solver however needs the serialization to be *per AKSlot*, i.e.
    we need to 'repeat' all preferences for each slot of an AK.

    Part of the implementation of the format of the KoMa solver:
    https://github.com/Die-KoMa/ak-plan-optimierung/wiki/Input-&-output-format#input--output-format
    """

    def create(self, validated_data):
        raise ValueError("`ExportAKPreferencePerSlotSerializer` is read-only.")

    def to_internal_value(self, data):
        raise ValueError("`ExportAKPreferencePerSlotSerializer` is read-only.")

    def update(self, instance, validated_data):
        raise ValueError("`ExportAKPreferencePerSlotSerializer` is read-only.")

    def to_representation(self, instance):
        preference_queryset = instance

        def _insert_akslot_id(serialization_dict: dict, slot: AKSlot) -> dict:
            """Insert id of the slot into the dict and return it."""

            # The naming scheme of the solver is confusing.
            # Our 'AKSlot' corresponds to the 'AK' of the solver,
            # so `ak_id` is the id of the corresponding AKSlot.
            serialization_dict["ak_id"] = slot.pk
            return serialization_dict

        return_lst = []
        for pref in preference_queryset:
            pref_serialization = ExportAKPreferenceSerializer(pref).data
            return_lst.extend([
                _insert_akslot_id(pref_serialization, slot)
                for slot in pref.ak.akslot_set.all()
            ])
        return return_lst


class ExportParticipantInfoSerializer(serializers.ModelSerializer):
    """Serializer of EventParticipant objects for the 'info' field.

    Used in `ExportParticipantSerializer` to serialize EventParticipant objects
    for the export to a solver. Part of the implementation of the
    format of the KoMa solver:
    https://github.com/Die-KoMa/ak-plan-optimierung/wiki/Input-&-output-format#input--output-format
    """
    name = serializers.CharField(source="__str__")

    class Meta:
        model = EventParticipant
        fields = ["name"]
        read_only_fields = ["name"]


class ExportParticipantSerializer(serializers.ModelSerializer):
    """Export serializer for EventParticipant objects.

    Used to serialize EventParticipant objects for the export to a solver.
    Part of the implementation of the format of the KoMa solver:
    https://github.com/Die-KoMa/ak-plan-optimierung/wiki/Input-&-output-format#input--output-format
    """

    room_constraints = StringListField(source="get_room_constraints")
    time_constraints = StringListField(source="get_time_constraints")
    preferences = ExportAKPreferencePerSlotSerializer(source="export_preferences")
    info = ExportParticipantInfoSerializer(source="*")

    class Meta:
        model = EventParticipant
        fields = ["id", "info", "room_constraints", "time_constraints", "preferences"]
        read_only_fields = ["id", "info", "room_constraints", "time_constraints", "preferences"]
