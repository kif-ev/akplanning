from collections.abc import Iterable

from rest_framework import serializers

from AKModel.availability.models import Availability
from AKModel.models import (
    AK,
    AKCategory,
    AKOwner,
    AKPreference,
    AKSlot,
    AKTrack,
    Event,
    EventParticipant,
    Room,
    TimeslotBlock,
)


class StringListField(serializers.ListField):
    child = serializers.CharField()


class IntListField(serializers.ListField):
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


class ExportRoomInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ["name"]
        read_only_fields = ["name"]


class ExportRoomSerializer(serializers.ModelSerializer):
    time_constraints = StringListField(source="get_time_constraints", read_only=True)
    fulfilled_room_constraints = StringListField(
        source="get_fulfilled_room_constraints", read_only=True
    )
    info = ExportRoomInfoSerializer(source="*")

    class Meta:
        model = Room
        fields = [
            "id",
            "capacity",
            "time_constraints",
            "fulfilled_room_constraints",
            "info",
        ]
        read_only_fields = [
            "id",
            "capacity",
            "time_constraints",
            "fulfilled_room_constraints",
            "info",
        ]


class ExportAKSlotInfoSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="ak.name")
    head = serializers.SerializerMethodField()
    reso = serializers.BooleanField(source="ak.reso")
    description = serializers.CharField(source="ak.description")
    duration_in_hours = serializers.FloatField(source="duration")
    django_ak_id = serializers.IntegerField(source="ak.pk")
    types = StringListField(source="type_names")

    def get_head(self, slot: AKSlot):
        return ", ".join([str(owner) for owner in slot.ak.owners.all()])

    class Meta:
        model = AKSlot
        fields = [
            "name",
            "head",
            "description",
            "reso",
            "duration_in_hours",
            "django_ak_id",
            "types",
        ]
        read_only_fields = [
            "name",
            "head",
            "description",
            "reso",
            "duration_in_hours",
            "django_ak_id",
            "types",
        ]


class ExportAKSlotPropertiesSerializer(serializers.ModelSerializer):
    conflicts = IntListField(source="conflict_pks")
    dependencies = IntListField(source="depencency_pks")

    class Meta:
        model = AKSlot
        fields = ["conflicts", "dependencies"]
        read_only_fields = ["conflicts", "dependencies"]


class ExportAKSlotSerializer(serializers.ModelSerializer):
    duration = serializers.IntegerField(source="export_duration")
    room_constraints = StringListField(source="get_room_constraints")
    time_constraints = StringListField(source="get_time_constraints")
    info = ExportAKSlotInfoSerializer(source="*")
    properties = ExportAKSlotPropertiesSerializer(source="*")

    class Meta:
        model = AKSlot
        fields = [
            "id",
            "duration",
            "properties",
            "room_constraints",
            "time_constraints",
            "info",
        ]
        read_only_fields = [
            "id",
            "duration",
            "properties",
            "room_constraints",
            "time_constraints",
            "info",
        ]


class ExportAKPreferenceSerializer(serializers.ModelSerializer):
    ak_id = serializers.IntegerField(source="slot.pk")
    required = serializers.BooleanField(source="required")
    preference_score = serializers.IntegerField(source="preference_score")

    class Meta:
        model = AKPreference
        fields = ["ak_id", "required", "preference_score"]
        read_only_fields = ["ak_id", "required", "preference_score"]


class ExportParticipantInfoSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="__str__")

    class Meta:
        model = EventParticipant
        fields = ["name"]
        read_only_fields = ["name"]


class ExportParticipantSerializer(serializers.ModelSerializer):
    room_constraints = StringListField(source="get_room_constraints")
    time_constraints = StringListField(source="get_time_constraints")
    preferences = ExportAKPreferenceSerializer(source="export_preferences", many=True)
    info = ExportParticipantInfoSerializer(source="*")

    class Meta:
        model = EventParticipant
        fields = ["id", "info", "room_constraints", "time_constraints", "preferences"]
        read_only_fields = ["id", "info", "room_constraints", "time_constraints", "preferences"]


class ExportParticipantAndDummiesSerializer(serializers.BaseSerializer):
    def to_representation(self, event: Event):
        real_participants = ExportParticipantSerializer(event.participants, many=True).data

        dummies = []
        if EventParticipant.objects.exists():
            next_participant_pk = EventParticipant.objects.latest("pk").pk + 1
        else:
            next_participant_pk = 1
        # add one dummy participant per owner
        # this ensures that the hard constraints from each owner are considered
        for new_pk, owner in enumerate(event.owners, next_participant_pk):
            owned_slots = event.slots.filter(ak__owners=owner).order_by().all()
            if not owned_slots:
                continue
            new_participant_data = {
                "id": new_pk,
                "info": {"name": f"{owner} [AKOwner]"},
                "room_constraints": [],
                "time_constraints": [],
                "preferences": [
                    {"ak_id": slot.pk, "required": True, "preference_score": -1}
                    for slot in owned_slots
                ]
            }
            dummies.append(new_participant_data)
        return real_participants + dummies


class ExportEventInfoSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source="name")
    contact_email = serializers.EmailField(required=False)
    place = serializers.CharField(required=False)

    class Meta:
        model = Event
        fields = ["title", "slug", "contact_email", "place"]


class ExportTimeslotBlockSerializer(serializers.BaseSerializer):
    def to_representation(self, blocks: Iterable[TimeslotBlock]):
        blocks = list(blocks)
        event = self.context["event"]

        def _check_event_not_covered(availabilities: list[Availability]) -> bool:
            """Test if event is not covered by availabilities."""
            return not Availability.is_event_covered(event, availabilities)

        def _check_akslot_fixed_in_timeslot(
            ak_slot: AKSlot, timeslot: Availability
        ) -> bool:
            """Test if an AKSlot is fixed to overlap a timeslot slot."""
            if not ak_slot.fixed or ak_slot.start is None:
                return False

            fixed_avail = Availability(
                event=event, start=ak_slot.start, end=ak_slot.end
            )
            return fixed_avail.overlaps(timeslot, strict=True)

        def _check_add_constraint(
            slot: Availability, availabilities: list[Availability]
        ) -> bool:
            """Test if object is not available for whole event and may happen during slot."""
            return _check_event_not_covered(availabilities) and slot.is_covered(
                availabilities
            )

        def _generate_time_constraints(
            avail_label: str,
            avail_dict: dict,
            timeslot_avail: Availability,
            prefix: str = "availability",
        ) -> list[str]:
            return [
                f"{prefix}-{avail_label}-{pk}"
                for pk, availabilities in avail_dict.items()
                if _check_add_constraint(timeslot_avail, availabilities)
            ]

        timeslots = {
            "info": {"duration": float(event.export_slot)},
            "blocks": [],
        }

        ak_availabilities = {
            ak.pk: Availability.union(ak.availabilities.all())
            for ak in AK.objects.filter(event=event).all()
        }
        room_availabilities = {
            room.pk: Availability.union(room.availabilities.all()) for room in event.rooms
        }
        person_availabilities = {
            person.pk: Availability.union(person.availabilities.all())
            for person in event.owners
        }
        participant_availabilities = {
            participant.pk: Availability.union(participant.availabilities.all())
            for participant in event.participants
        }

        block_names = []
        for block_idx, block in enumerate(blocks):
            current_block = []

            if not block:
                continue

            block_start = block[0].avail.start.astimezone(event.timezone)
            block_end = block[-1].avail.end.astimezone(event.timezone)

            start_day = block_start.strftime("%A, %d. %b")
            if block_start.date() == block_end.date():
                # same day
                time_str = (
                    block_start.strftime("%H:%M") + " - " + block_end.strftime("%H:%M")
                )
            else:
                # different days
                time_str = (
                    block_start.strftime("%a %H:%M")
                    + " - "
                    + block_end.strftime("%a %H:%M")
                )
            block_names.append([start_day, time_str])

            block_timeconstraints = [
                f"notblock{idx}" for idx in range(len(blocks)) if idx != block_idx
            ]

            for timeslot in block:
                time_constraints = []
                # if reso_deadline is set and timeslot ends before it,
                #   add fulfilled time constraint 'resolution'
                if (
                    event.reso_deadline is None
                    or timeslot.avail.end < event.reso_deadline
                ):
                    time_constraints.append("resolution")

                # add fulfilled time constraints for all AKs that cannot happen during full event
                time_constraints.extend(
                    _generate_time_constraints("ak", ak_availabilities, timeslot.avail)
                )

                # add fulfilled time constraints for all persons that are not available for full event
                time_constraints.extend(
                    _generate_time_constraints(
                        "person", person_availabilities, timeslot.avail
                    )
                )

                # add fulfilled time constraints for all rooms that are not available for full event
                time_constraints.extend(
                    _generate_time_constraints(
                        "room", room_availabilities, timeslot.avail
                    )
                )

                # add fulfilled time constraints for all participants that are not available for full event
                time_constraints.extend(
                    _generate_time_constraints(
                        "participant", participant_availabilities, timeslot.avail
                    )
                )

                # add fulfilled time constraints for all AKSlots fixed to happen during timeslot
                time_constraints.extend(
                    [
                        f"fixed-akslot-{slot.id}"
                        for slot in AKSlot.objects.filter(
                            event=event, fixed=True
                        ).exclude(start__isnull=True)
                        if _check_akslot_fixed_in_timeslot(slot, timeslot.avail)
                    ]
                )

                time_constraints.extend(timeslot.constraints)
                time_constraints.extend(block_timeconstraints)
                time_constraints.sort()

                current_block.append(
                    {
                        "id": timeslot.idx,
                        "info": {
                            "start": timeslot.avail.start.astimezone(
                                event.timezone
                            ).strftime("%Y-%m-%d %H:%M"),
                            "end": timeslot.avail.end.astimezone(
                                event.timezone
                            ).strftime("%Y-%m-%d %H:%M"),
                        },
                        "fulfilled_time_constraints": time_constraints,
                    }
                )

            timeslots["blocks"].append(current_block)

        timeslots["info"]["blocknames"] = block_names

        return timeslots


class ExportEventSerializer(serializers.ModelSerializer):
    info = ExportEventInfoSerializer(source="*")
    rooms = ExportRoomSerializer(many=True)
    aks = ExportAKSlotSerializer(source="slots", many=True)
    participants = ExportParticipantAndDummiesSerializer(source="*")
    timeslots = ExportTimeslotBlockSerializer(source="discretize_timeslots")

    class Meta:
        model = Event
        fields = ["participants", "rooms", "timeslots", "info", "aks"]
        read_only_fields = ["participants", "rooms", "timeslots", "info", "aks"]
