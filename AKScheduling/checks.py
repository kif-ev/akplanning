import itertools

from AKModel.models import Event


def aks_with_unfulfillable_requirements(event: Event):
    """Get all AKs that have unfulfillable requirements.

    An AK has unfulfillable requirements if there is no room in the event that fullfills all of its requirements.

    :param event: Event to check
    :return: List of all AKs with unfulfillable requirements.
    :rtype: List[AK]
    """
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
    for ak in event.ak_set.prefetch_related('requirements').all():
        ak_properties = '&'.join(str(r.pk) for r in ak.requirements.all())
        if ak_properties == '':
            continue
        if not ak_properties in rooms_properties_encoded:
            aks_not_possible.append(ak)
    return aks_not_possible
