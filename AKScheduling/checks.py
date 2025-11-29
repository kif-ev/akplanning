import itertools
from datetime import timedelta

from AKModel.models import Event


def aks_with_unfulfillable_requirements(event: Event, qs = None):
    """Get all AKs that have unfulfillable requirements.

    An AK has unfulfillable requirements if there is no room in the event that fullfills all of its requirements.

    :param event: Event to check
    :param qs: Queryset of AKs to check. If None, all AKs of the event are checked.
    :return: List of all AKs with unfulfillable requirements.
    :rtype: List[AK]
    """
    if qs is None:
        qs = event.ak_set

    # Build a list of all combinations of room properties which are fulfilled by at least one room
    rooms_properties_encoded = set()
    for room in event.rooms.prefetch_related('properties'):
        rp_pks = [str(p.pk) for p in room.properties.all()]
        if len(rp_pks) == 0:
            continue
        encoded = '&'.join(rp_pks)
        # No need to continue with this room if properties are already fulfilled by another room
        if encoded in rooms_properties_encoded:
            continue
        # Add all properties of this room...
        rooms_properties_encoded.add(encoded)
        # ...as well as all subsets of these properties
        for length in range(1, len(rp_pks)):
            for subset in itertools.combinations(rp_pks, length):
                rooms_properties_encoded.add('&'.join(subset))

    # Loop over all AKs and check whether their requirements are fulfilled by at least one room
    aks_not_possible = []
    for ak in qs.prefetch_related('requirements').all():
        ak_properties = '&'.join(str(r.pk) for r in ak.requirements.all())
        if ak_properties == '':
            continue
        if not ak_properties in rooms_properties_encoded:
            aks_not_possible.append(ak)
    return aks_not_possible

def aks_too_big(event: Event, qs = None):
    """
    Get all AKs that are too big to fit into any room of the event.

    :param event: Event to check
    :param qs: Queryset of AKs to check. If None, all AKs of the event are checked.
    :return: List of all AKs that are too big to fit into any room.
    :rtype: List[AK]
    """
    if qs is None:
        qs = event.ak_set

    # Get the maximum capacity of all rooms of the event
    biggest_room = event.rooms.order_by('-capacity').first()
    if biggest_room is None:
        return []
    max_room_capacity = biggest_room.capacity

    # Loop over all AKs and check whether they fit into at least one room
    aks_too_big = []
    for ak in qs.all():
        if ak.interest > max_room_capacity:
            aks_too_big.append(ak)
    return aks_too_big


def aks_not_in_default_schedules(event: Event, qs = None):
    """
    Get all AKs without any availabilities inside the default schedules
    (strict and those inside default slots but not ones matching their category)

    :param event: Event to check
    :param qs: Queryset of AKs to check. If None, all AKs of the event are checked.
    :return: Two lists AKs, first those that cannot be placed in any default slot,
             second those that can only be placed in a slot not machting their category.
    :rtype: List[AK], List[AK]
    """
    if qs is None:
        qs = event.ak_set

    aks_no_slot = []
    aks_no_category_matching_slot = []

    default_slots = list(event.defaultslot_set.prefetch_related('primary_categories').all())

    # For every AK of the event
    for ak in qs.prefetch_related('availabilities', 'akslot_set'):
        if ak.akslot_set.count() == 0:
            continue
        duration_longest_slot = timedelta(hours=float(max(slot.duration for slot in ak.akslot_set.all())))
        found_slot = False
        found_slot_of_matching_category = False
        for a in ak.availabilities.all():
            for default_slot in default_slots:
                # Compute overlap of availability and default slot
                overlap_start = max(a.start, default_slot.start)
                overlap_end = min(a.end, default_slot.end)
                overlap_duration = overlap_end - overlap_start
                # Check whether overlap is long enough to place the AK
                if overlap_duration >= duration_longest_slot:
                    found_slot = True
                    # Does even the category match?
                    if ak.category in default_slot.primary_categories.all():
                        # Then we can stop early
                        found_slot_of_matching_category = True
                        break
            if found_slot_of_matching_category:
                break
        if not found_slot:
            aks_no_slot.append(ak)
        elif not found_slot_of_matching_category:
            aks_no_category_matching_slot.append(ak)
    return aks_no_slot, aks_no_category_matching_slot
