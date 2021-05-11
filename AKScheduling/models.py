from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver

from AKModel.availability.models import Availability
from AKModel.models import AK, AKSlot, Room, Event, AKOwner, ConstraintViolation


def update_constraint_violations(new_violations, existing_violations_to_check):
    """
    Update existing constraint violations (subset for which new violations were computed) based on these new violations.
    This will add all new violations without a match, preserve the matching ones
    and delete the obsolete ones (those without a match from the newly calculated violations).

    :param new_violations: list of new (not yet saved) violations that exist after the last change
    :type new_violations: list[ConstraintViolation]
    :param existing_violations_to_check: list of related violations currently in the db
    :type existing_violations_to_check: list[ConstraintViolation]
    """
    for new_violation in new_violations:
        found_match = False
        for existing_violation in existing_violations_to_check:
            if existing_violation.matches(new_violation):
                # Remove from existing violations set since it should stay in db
                existing_violations_to_check.remove(existing_violation)
                found_match = True
                break

        # Only save new violation if no match was found
        if not found_match:
            new_violation.save()

    # Cleanup obsolete violations (ones without matches computed under current conditions)
    for outdated_violation in existing_violations_to_check:
        outdated_violation.delete()


@receiver(post_save, sender=AK)
def ak_changed_handler(sender, instance: AK, **kwargs):
    # Changes might affect: Owner(s), Requirements, Conflicts, Prerequisites, Category, Interest
    pass


@receiver(m2m_changed, sender=AK.owners.through)
def ak_changed_handler(sender, instance: AK, action: str, **kwargs):
    """
    Owners of AK changed
    """
    # Only signal after change (post_add, post_delete, post_clear) are relevant
    if not action.startswith("post"):
        return

    # print(f"{instance} changed")

    event = instance.event

    # Owner(s) changed: Might affect multiple AKs by the same owner(s) at the same time
    violation_type = ConstraintViolation.ViolationType.OWNER_TWO_SLOTS
    new_violations = []

    slots_of_this_ak: [AKSlot] = instance.akslot_set.filter(start__isnull=False)

    # For all owners (after recent change)...
    for owner in instance.owners.all():
        # ...find other slots that might be overlapping...

        for ak in owner.ak_set.all():
            # ...find overlapping slots...
            if ak != instance:
                for slot in slots_of_this_ak:
                    for other_slot in ak.akslot_set.filter(start__isnull=False):
                        if slot.overlaps(other_slot):
                            # ...and create a temporary violation if necessary...
                            c = ConstraintViolation(
                                type=violation_type,
                                level=ConstraintViolation.ViolationLevel.VIOLATION,
                                event=event,
                                ak_owner=owner
                            )
                            c.aks_tmp.add(instance)
                            c.aks_tmp.add(other_slot.ak)
                            c.ak_slots_tmp.add(slot)
                            c.ak_slots_tmp.add(other_slot)
                            new_violations.append(c)

        # print(f"{owner} has the following conflicts: {new_violations}")

    # ... and compare to/update list of existing violations of this type
    # belonging to the AK that was recently changed (important!)
    existing_violations_to_check = list(instance.constraintviolation_set.filter(type=violation_type))
    # print(existing_violations_to_check)
    update_constraint_violations(new_violations, existing_violations_to_check)


@receiver(post_save, sender=AKSlot)
def akslot_changed_handler(sender, instance: AKSlot, **kwargs):
    # Changes might affect: Duplicate parallel, Two in room, Resodeadline
    print(f"{sender} changed")
    event = instance.event

    # == Check for two parallel slots by one of the owners ==

    violation_type = ConstraintViolation.ViolationType.OWNER_TWO_SLOTS
    new_violations = []

    # For all owners (after recent change)...
    for owner in instance.ak.owners.all():
        # ...find other slots that might be overlapping...

        for ak in owner.ak_set.all():
            # ...find overlapping slots...
            if ak != instance.ak:
                for other_slot in ak.akslot_set.filter(start__isnull=False):
                    if instance.overlaps(other_slot):
                        # ...and create a temporary violation if necessary...
                        c = ConstraintViolation(
                            type=violation_type,
                            level=ConstraintViolation.ViolationLevel.VIOLATION,
                            event=event,
                            ak_owner=owner
                        )
                        c.aks_tmp.add(instance.ak)
                        c.aks_tmp.add(other_slot.ak)
                        c.ak_slots_tmp.add(instance)
                        c.ak_slots_tmp.add(other_slot)
                        new_violations.append(c)

        print(f"{owner} has the following conflicts: {new_violations}")

    # ... and compare to/update list of existing violations of this type
    # belonging to the AK that was recently changed (important!)
    existing_violations_to_check = list(instance.constraintviolation_set.filter(type=violation_type))
    print(existing_violations_to_check)
    update_constraint_violations(new_violations, existing_violations_to_check)

    # == Check for two aks in the same room at the same time ==

    violation_type = ConstraintViolation.ViolationType.ROOM_TWO_SLOTS
    new_violations = []

    # For all slots in this room...
    for other_slot in instance.room.akslot_set.all():
        if other_slot != instance:
            # ... find overlapping slots...
            if instance.overlaps(other_slot):
                # ...and create a temporary violation if necessary...
                c = ConstraintViolation(
                    type=violation_type,
                    level=ConstraintViolation.ViolationLevel.WARNING,
                    event=event,
                    room=instance.room
                )
                c.ak_slots_tmp.add(instance)
                c.ak_slots_tmp.add(other_slot)
                new_violations.append(c)

    print(f"Multiple slots in room {instance.room}: {new_violations}")

    # ... and compare to/update list of existing violations of this type
    # belonging to the AK that was recently changed (important!)
    existing_violations_to_check = list(instance.room.constraintviolation_set.filter(type=violation_type))
    print(existing_violations_to_check)
    update_constraint_violations(new_violations, existing_violations_to_check)


@receiver(post_save, sender=Room)
def room_changed_handler(sender, **kwargs):
    # Changes might affect: Room size, Requirement
    print(f"{sender} changed")
    # TODO Replace with real handling


@receiver(post_save, sender=Availability)
def availability_changed_handler(sender, **kwargs):
    # Changes might affect: category availability, AK availability, Room availability
    print(f"{sender} changed")
    # TODO Replace with real handling


@receiver(post_save, sender=Event)
def room_changed_handler(sender, **kwargs):
    # Changes might affect: Reso-Deadline
    print(f"{sender} changed")
    # TODO Replace with real handling
