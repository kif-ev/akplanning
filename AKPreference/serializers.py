from rest_framework import serializers

from AKModel.models import AKSlot
from AKModel.serializers import StringListField
from AKPreference.models import EventParticipant


def _preferences_per_slot(preferences, exclude_slot_pks: set[int]) -> list[dict]:
    """Serialize AKPreferences per slot of their AK for the export to a solver.

    The AKPreference model stores the preference per AK object.
    The solver however needs the serialization to be *per AKSlot*, i.e.
    we need to 'repeat' all preferences for each slot of an AK.

    Part of the implementation of the format of the KoMa solver:
    https://github.com/Die-KoMa/ak-plan-optimierung/wiki/Input-&-output-format#input--output-format

    :param preferences: preferences to serialize (with prefetched slots of their AKs)
    :param exclude_slot_pks: pks of slots to skip
    """
    # The naming scheme of the solver is confusing.
    # Our 'AKSlot' corresponds to the 'AK' of the solver,
    # so `ak_id` is the id of the corresponding AKSlot.
    return [
        {"ak_id": slot.pk, "required": pref.required, "preference_score": pref.preference_score}
        for pref in preferences
        for slot in pref.ak.akslot_set.all()
        if slot.pk not in exclude_slot_pks
    ]


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
    time_constraints = serializers.SerializerMethodField()
    preferences = serializers.SerializerMethodField()
    info = ExportParticipantInfoSerializer(source="*")

    def _has_required_preferences(self, participant: EventParticipant) -> bool:
        """Whether the participant has 'Required' preferences.

        The pks of all such participants can be passed via the context key `participants_with_required_preferences`
        to avoid querying this per participant.
        """
        if "participants_with_required_preferences" in self.context:
            return participant.pk in self.context["participants_with_required_preferences"]
        return participant.has_required_preferences

    def get_time_constraints(self, participant: EventParticipant) -> list[str]:
        """Get serialized representation for time_constraints.

        Stored availabilities of participants are only exported if they have 'Required' preferences
        (no longer selectable, but still exported as hard constraints): The availabilities of AK owners
        are already exported as time constraints of their AKs.
        Adjusted availabilities can be passed via the context key `participant_availabilities`
        (mapping participant pks to availabilities), e.g. because scheduled slots of the AKs of their linked
        AK owner or of AKs they are required for are not exported but must still block these times.
        """
        # pylint: disable=import-outside-toplevel
        from AKModel.availability.models import Availability

        participant_availabilities = self.context.get("participant_availabilities", {})
        if participant.pk in participant_availabilities:
            avails = participant_availabilities[participant.pk]
        elif self._has_required_preferences(participant):
            avails = list(participant.availabilities.all())
            if not avails:
                # no stored availabilities -> participant is available for the whole event
                return []
        else:
            return []
        if Availability.is_event_covered(participant.event, avails):
            return []
        return [f"availability-participant-{participant.pk}"]

    def get_preferences(self, participant: EventParticipant) -> list[dict]:
        """Get serialized representation for preferences.

        If the participant is linked to an AK owner, the participant is marked as required
        for all slots of the AKs of that owner. Since a participant cannot attend multiple AKs at the same time,
        this makes the slots of their own AKs bad times for the AKs they would like to attend.
        These entries replace the preferences of the participant for their own AKs.

        The slots of each owner can be passed via the context key `owned_slot_pks`
        (mapping AKOwner pks to sets of slot pks) to avoid querying them per participant.
        """
        owned_slot_pks = set()
        if participant.ak_owner_id is not None:
            if "owned_slot_pks" in self.context:
                owned_slot_pks = self.context["owned_slot_pks"].get(participant.ak_owner_id, set())
            else:
                owned_slot_pks = set(
                        AKSlot.objects.filter(event=participant.event, ak__owners=participant.ak_owner_id)
                        .order_by().values_list("pk", flat=True)
                )
        preferences = _preferences_per_slot(participant.export_preferences, exclude_slot_pks=owned_slot_pks)
        preferences.extend({"ak_id": slot_pk, "required": True, "preference_score": -1}
                           for slot_pk in sorted(owned_slot_pks))
        return preferences

    class Meta:
        model = EventParticipant
        fields = ["id", "info", "room_constraints", "time_constraints", "preferences"]
        read_only_fields = ["id", "info", "room_constraints", "time_constraints", "preferences"]
