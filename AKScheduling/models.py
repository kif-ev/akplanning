# This file mainly contains signal receivers, which follow a very strong interface, having e.g., a sender attribute
# that is hardly used by us. Nevertheless, to follow the django receiver coding style and since changes might
# cause issues when loading fixtures or model dumps, it is not wise to replace that attribute with "_".
# Therefore, the check that finds unused arguments is disabled for this whole file:
# pylint: disable=unused-argument
from typing import Iterable

from django.db.models.signals import post_save, m2m_changed, pre_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from AKModel.availability.models import Availability
from AKModel.models import AK, AKSlot, Room, Event, ConstraintViolation


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


def update_cv_reso_deadline_for_slot(slot):
    """
    Update constraint violation AK_AFTER_RESODEADLINE for given slot

    :param slot: slot to check/update
    :type slot: AKSlot
    """
    event = slot.event

    # Update only if reso_deadline exists
    # if event was changed and reso_deadline is removed, CVs will be deleted by event changed handler
    # Update only has to be done for already scheduled slots with reso intention
    if slot.ak.reso and slot.event.reso_deadline and slot.start:
        violation_type = ConstraintViolation.ViolationType.AK_AFTER_RESODEADLINE
        new_violations = []

        # Violation?
        if slot.end > event.reso_deadline:
            c = ConstraintViolation(
                type=violation_type,
                level=ConstraintViolation.ViolationLevel.VIOLATION,
                event=event,
            )
            c.aks_tmp.add(slot.ak)
            c.ak_slots_tmp.add(slot)
            new_violations.append(c)
        update_constraint_violations(new_violations, list(slot.constraintviolation_set.filter(type=violation_type)))


def check_capacity_for_slot(slot: AKSlot):
    """
    Check whether this slot violates the capacity requirement

    :param slot: slot to check
    :type slot: AKSlot
    :return: Violation (if any) or None
    :rtype: ConstraintViolation or None
    """

    # If slot is scheduled in a room and interest was specified
    if slot.room and slot.room.capacity >= 0 and slot.ak.interest >= 0:
        # Create a violation if interest exceeds room capacity
        if slot.room.capacity < slot.ak.interest:
            c = ConstraintViolation(
                type=ConstraintViolation.ViolationType.ROOM_CAPACITY_EXCEEDED,
                level=ConstraintViolation.ViolationLevel.VIOLATION,
                event=slot.event,
                room=slot.room,
                comment=_("Not enough space for AK interest (Interest: %(interest)d, Capacity: %(capacity)d)")
                        % {'interest': slot.ak.interest, 'capacity': slot.room.capacity},
            )
            c.ak_slots_tmp.add(slot)
            c.aks_tmp.add(slot.ak)
            return c

        # Create a warning if interest is close to room capacity
        if slot.room.capacity < slot.ak.interest + 5 or slot.room.capacity < slot.ak.interest * 1.25:
            c = ConstraintViolation(
                type=ConstraintViolation.ViolationType.ROOM_CAPACITY_EXCEEDED,
                level=ConstraintViolation.ViolationLevel.WARNING,
                event=slot.event,
                room=slot.room,
                comment=_("Space is too close to AK interest (Interest: %(interest)d, Capacity: %(capacity)d)")
                        % {'interest': slot.ak.interest, 'capacity': slot.room.capacity}
            )
            c.ak_slots_tmp.add(slot)
            c.aks_tmp.add(slot.ak)
            return c

    return None


@receiver(post_save, sender=AK)
def ak_changed_handler(sender, instance: AK, **kwargs):
    """
    Signal receiver: Check for violations after AK changed

    Changes might affect: Reso intention, Category, Interest
    """
    # TODO Reso intention changes

    # Check room capacities
    violation_type = ConstraintViolation.ViolationType.ROOM_CAPACITY_EXCEEDED
    new_violations = []
    for slot in instance.akslot_set.all():
        cv = check_capacity_for_slot(slot)
        if cv is not None:
            new_violations.append(cv)

    existing_violations_to_check = list(instance.constraintviolation_set.filter(type=violation_type))
    update_constraint_violations(new_violations, existing_violations_to_check)


@receiver(m2m_changed, sender=AK.owners.through)
def ak_owners_changed_handler(sender, instance: AK, action: str, **kwargs):
    """
    Signal receiver: Owners of AK changed
    """
    # Only signal after change (post_add, post_delete, post_clear) are relevant
    if not action.startswith("post"):
        return

    event = instance.event

    # Owner(s) changed: Might affect multiple AKs by the same owner(s) at the same time
    violation_type = ConstraintViolation.ViolationType.OWNER_TWO_SLOTS
    new_violations = []

    slots_of_this_ak: Iterable[AKSlot] = instance.akslot_set.filter(start__isnull=False)

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

    # ... and compare to/update list of existing violations of this type
    # belonging to the AK that was recently changed (important!)
    existing_violations_to_check = list(instance.constraintviolation_set.filter(type=violation_type))
    # print(existing_violations_to_check)
    update_constraint_violations(new_violations, existing_violations_to_check)


@receiver(m2m_changed, sender=AK.conflicts.through)
def ak_conflicts_changed_handler(sender, instance: AK, action: str, **kwargs):
    """
    Signal receiver: Conflicts of AK changed
    """
    # Only signal after change (post_add, post_delete, post_clear) are relevant
    if not action.startswith("post"):
        return

    event = instance.event

    # Conflict(s) changed: Might affect multiple AKs that are conflicts of each other
    violation_type = ConstraintViolation.ViolationType.AK_CONFLICT_COLLISION
    new_violations = []

    slots_of_this_ak: Iterable[AKSlot] = instance.akslot_set.filter(start__isnull=False)
    conflicts_of_this_ak: Iterable[AK] = instance.conflicts.all()

    # Loop over all existing conflicts
    for ak in conflicts_of_this_ak:
        if ak != instance:
            for other_slot in ak.akslot_set.filter(start__isnull=False):
                for slot in slots_of_this_ak:
                    # ...find overlapping slots...
                    if slot.overlaps(other_slot):
                        # ...and create a temporary violation if necessary...
                        c = ConstraintViolation(
                            type=violation_type,
                            level=ConstraintViolation.ViolationLevel.VIOLATION,
                            event=event,
                        )
                        c.aks_tmp.add(instance)
                        c.ak_slots_tmp.add(slot)
                        c.ak_slots_tmp.add(other_slot)
                        new_violations.append(c)

    # ... and compare to/update list of existing violations of this type
    # belonging to the AK that was recently changed (important!)
    existing_violations_to_check = list(instance.constraintviolation_set.filter(type=violation_type))
    # print(existing_violations_to_check)
    update_constraint_violations(new_violations, existing_violations_to_check)


@receiver(m2m_changed, sender=AK.prerequisites.through)
def ak_prerequisites_changed_handler(sender, instance: AK, action: str, **kwargs):
    """
    Signal receiver: Prerequisites of AK changed
    """
    # Only signal after change (post_add, post_delete, post_clear) are relevant
    if not action.startswith("post"):
        return

    event = instance.event

    # Prerequisite(s) changed: Might affect multiple AKs that should have a certain order
    violation_type = ConstraintViolation.ViolationType.AK_BEFORE_PREREQUISITE
    new_violations = []

    slots_of_this_ak: Iterable[AKSlot] = instance.akslot_set.filter(start__isnull=False)
    prerequisites_of_this_ak: Iterable[AK] = instance.prerequisites.all()

    # Loop over all prerequisites
    for ak in prerequisites_of_this_ak:
        if ak != instance:
            for other_slot in ak.akslot_set.filter(start__isnull=False):
                for slot in slots_of_this_ak:
                    # ...find overlapping slots...
                    if other_slot.end > slot.start:
                        # ...and create a temporary violation if necessary...
                        c = ConstraintViolation(
                            type=violation_type,
                            level=ConstraintViolation.ViolationLevel.VIOLATION,
                            event=event,
                        )
                        c.aks_tmp.add(instance)
                        c.ak_slots_tmp.add(slot)
                        c.ak_slots_tmp.add(other_slot)
                        new_violations.append(c)

    # ... and compare to/update list of existing violations of this type
    # belonging to the AK that was recently changed (important!)
    existing_violations_to_check = list(instance.constraintviolation_set.filter(type=violation_type))
    # print(existing_violations_to_check)
    update_constraint_violations(new_violations, existing_violations_to_check)


@receiver(m2m_changed, sender=AK.requirements.through)
def ak_requirements_changed_handler(sender, instance: AK, action: str, **kwargs):
    """
    Signal receiver: Requirements of AK changed
    """
    # Only signal after change (post_add, post_delete, post_clear) are relevant
    if not action.startswith("post"):
        return

    event = instance.event

    # Requirement(s) changed: Might affect slots and rooms
    violation_type = ConstraintViolation.ViolationType.REQUIRE_NOT_GIVEN
    new_violations = []

    slots_of_this_ak: Iterable[AKSlot] = instance.akslot_set.filter(start__isnull=False)

    # For all requirements (after recent change)...
    for slot in slots_of_this_ak:

        room = slot.room
        if room is None:
            continue
        room_requirements = room.properties.all()

        for requirement in instance.requirements.all():

            if not requirement in room_requirements:
                # ...and create a temporary violation if necessary...
                c = ConstraintViolation(
                    type=violation_type,
                    level=ConstraintViolation.ViolationLevel.VIOLATION,
                    event=event,
                    requirement=requirement,
                    room=room,
                )
                c.aks_tmp.add(instance)
                c.ak_slots_tmp.add(slot)
                new_violations.append(c)

    # ... and compare to/update list of existing violations of this type
    # belonging to the AK that was recently changed (important!)
    existing_violations_to_check = list(instance.constraintviolation_set.filter(type=violation_type))
    # print(existing_violations_to_check)
    update_constraint_violations(new_violations, existing_violations_to_check)


@receiver(post_save, sender=AKSlot)
def akslot_changed_handler(sender, instance: AKSlot, **kwargs):
    """
    Signal receiver: AKSlot changed

    Changes might affect: Duplicate parallel, Two in room, Resodeadline
    """
    # TODO Consider rewriting this very long and complex method to resolve several (style) issues:
    # pylint: disable=too-many-nested-blocks,too-many-locals,too-many-branches,too-many-statements
    event = instance.event

    # == Check for two parallel slots by one of the owners ==

    violation_type = ConstraintViolation.ViolationType.OWNER_TWO_SLOTS
    new_violations = []

    if instance.start:
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

    # ... and compare to/update list of existing violations of this type
    # belonging to the AK that was recently changed (important!)
    existing_violations_to_check = list(instance.constraintviolation_set.filter(type=violation_type))
    # print(existing_violations_to_check)
    update_constraint_violations(new_violations, existing_violations_to_check)

    # == Check for two aks in the same room at the same time ==

    violation_type = ConstraintViolation.ViolationType.ROOM_TWO_SLOTS
    new_violations = []

    # For all slots in this room...
    if instance.room and instance.start:
        for other_slot in instance.room.akslot_set.filter(start__isnull=False):
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
                    c.aks_tmp.add(instance.ak)
                    c.aks_tmp.add(other_slot.ak)
                    c.ak_slots_tmp.add(instance)
                    c.ak_slots_tmp.add(other_slot)
                    new_violations.append(c)

    # ... and compare to/update list of existing violations of this type
    # belonging to the slot that was recently changed (important!)
    existing_violations_to_check = list(instance.constraintviolation_set.filter(type=violation_type))
    # print(existing_violations_to_check)
    update_constraint_violations(new_violations, existing_violations_to_check)

    # == Check for reso ak after reso deadline ==

    update_cv_reso_deadline_for_slot(instance)

    # == Check for two slots of the same AK at the same time (warning) ==

    violation_type = ConstraintViolation.ViolationType.AK_SLOT_COLLISION
    new_violations = []

    if instance.start:
        # For all other slots of this ak...
        for other_slot in instance.ak.akslot_set.filter(start__isnull=False):
            if other_slot != instance:
                # ... find overlapping slots...
                if instance.overlaps(other_slot):
                    # ...and create a temporary violation if necessary...
                    c = ConstraintViolation(
                        type=violation_type,
                        level=ConstraintViolation.ViolationLevel.WARNING,
                        event=event,
                    )
                    c.aks_tmp.add(instance.ak)
                    c.ak_slots_tmp.add(instance)
                    c.ak_slots_tmp.add(other_slot)
                    new_violations.append(c)

    # ... and compare to/update list of existing violations of this type
    # belonging to the slot that was recently changed (important!)
    existing_violations_to_check = list(instance.constraintviolation_set.filter(type=violation_type))
    update_constraint_violations(new_violations, existing_violations_to_check)

    # == Check for slot outside availability ==

    # An AK's availability changed: Might affect AK slots scheduled outside the permitted time
    violation_type = ConstraintViolation.ViolationType.SLOT_OUTSIDE_AVAIL
    new_violations = []

    if instance.start:
        availabilities_of_this_ak: Iterable[Availability] = instance.ak.availabilities.all()

        covered = False

        for availability in availabilities_of_this_ak:
            covered = availability.start <= instance.start and availability.end >= instance.end
            if covered:
                break
        if not covered:
            c = ConstraintViolation(
                type=violation_type,
                level=ConstraintViolation.ViolationLevel.VIOLATION,
                event=event
            )
            c.aks_tmp.add(instance.ak)
            c.ak_slots_tmp.add(instance)
            new_violations.append(c)

    # ... and compare to/update list of existing violations of this type
    # belonging to the AK that was recently changed (important!)
    existing_violations_to_check = list(instance.constraintviolation_set.filter(type=violation_type))
    # print(existing_violations_to_check)
    update_constraint_violations(new_violations, existing_violations_to_check)

    # == Check for requirement not fulfilled by room ==

    # Room(s) changed: Might affect slots and rooms
    violation_type = ConstraintViolation.ViolationType.REQUIRE_NOT_GIVEN
    new_violations = []

    if instance.room:

        room_requirements = instance.room.properties.all()

        for requirement in instance.ak.requirements.all():

            if requirement not in room_requirements:
                # ...and create a temporary violation if necessary...
                c = ConstraintViolation(
                    type=violation_type,
                    level=ConstraintViolation.ViolationLevel.VIOLATION,
                    event=event,
                    requirement=requirement,
                    room=instance.room,
                )
                c.aks_tmp.add(instance.ak)
                c.ak_slots_tmp.add(instance)
                new_violations.append(c)

    # ... and compare to/update list of existing violations of this type
    # belonging to the AK that was recently changed (important!)
    existing_violations_to_check = list(instance.constraintviolation_set.filter(type=violation_type))
    # print(existing_violations_to_check)
    update_constraint_violations(new_violations, existing_violations_to_check)

    # == check for simultaneous slots of conflicting AKs ==

    violation_type = ConstraintViolation.ViolationType.AK_CONFLICT_COLLISION
    new_violations = []

    if instance.start:
        conflicts_of_this_ak: Iterable[AK] = instance.ak.conflicts.all()

        for ak in conflicts_of_this_ak:
            if ak != instance.ak:
                for other_slot in ak.akslot_set.filter(start__isnull=False):
                    # ...find overlapping slots...
                    if instance.overlaps(other_slot):
                        # ...and create a temporary violation if necessary...
                        c = ConstraintViolation(
                            type=violation_type,
                            level=ConstraintViolation.ViolationLevel.VIOLATION,
                            event=event,
                        )
                        c.aks_tmp.add(instance.ak)
                        c.ak_slots_tmp.add(instance)
                        c.ak_slots_tmp.add(other_slot)
                        new_violations.append(c)

    # ... and compare to/update list of existing violations of this type
    # belonging to the AK that was recently changed (important!)
    existing_violations_to_check = list(instance.ak.constraintviolation_set.filter(type=violation_type))
    # print(existing_violations_to_check)
    update_constraint_violations(new_violations, existing_violations_to_check)

    # == check for missing prerequisites ==

    violation_type = ConstraintViolation.ViolationType.AK_BEFORE_PREREQUISITE
    new_violations = []

    if instance.start:
        prerequisites_of_this_ak: Iterable[AK] = instance.ak.prerequisites.all()

        for ak in prerequisites_of_this_ak:
            if ak != instance.ak:
                for other_slot in ak.akslot_set.filter(start__isnull=False):
                    # ...find slots in the wrong order...
                    if other_slot.end > instance.start:
                        # ...and create a temporary violation if necessary...
                        c = ConstraintViolation(
                            type=violation_type,
                            level=ConstraintViolation.ViolationLevel.VIOLATION,
                            event=event,
                        )
                        c.aks_tmp.add(instance.ak)
                        c.ak_slots_tmp.add(instance)
                        c.ak_slots_tmp.add(other_slot)
                        new_violations.append(c)

    # ... and compare to/update list of existing violations of this type
    # belonging to the AK that was recently changed (important!)
    existing_violations_to_check = list(instance.ak.constraintviolation_set.filter(type=violation_type))
    # print(existing_violations_to_check)
    update_constraint_violations(new_violations, existing_violations_to_check)

    # == Check for room capacity ==
    cv = check_capacity_for_slot(instance)
    new_violations = [cv] if cv is not None else []

    # Compare to/update list of existing violations of this type for this slot
    existing_violations_to_check = list(
        instance.constraintviolation_set.filter(type=ConstraintViolation.ViolationType.ROOM_CAPACITY_EXCEEDED)
    )
    update_constraint_violations(new_violations, existing_violations_to_check)


@receiver(pre_delete, sender=AKSlot)
def akslot_deleted_handler(sender, instance: AKSlot, **kwargs):
    """
    Signal receiver: AKSlot deleted

    Manually clean up or remove constraint violations that belong to this slot since there is no cascade deletion
    for many2many relationships. Explicitly listening for AK deletion signals is not necessary since they will
    transitively trigger this signal and we always set both AK and AKSlot references in a constraint violation
    """
    # print(f"{instance} deleted")

    for cv in instance.constraintviolation_set.all():
        # Make sure not delete CVs that e.g., show three parallel slots in a single room
        if cv.ak_slots.count() <= 2:
            cv.delete()


@receiver(post_save, sender=Room)
def room_changed_handler(sender, instance: Room, **kwargs):
    """
    Signal receiver: Room changed

    Changes might affect: Room size
    """
    # Check room capacities
    violation_type = ConstraintViolation.ViolationType.ROOM_CAPACITY_EXCEEDED
    new_violations = []
    for slot in instance.akslot_set.all():
        cv = check_capacity_for_slot(slot)
        if cv is not None:
            new_violations.append(cv)

    existing_violations_to_check = list(instance.constraintviolation_set.filter(type=violation_type))
    update_constraint_violations(new_violations, existing_violations_to_check)


@receiver(m2m_changed, sender=Room.properties.through)
def room_requirements_changed_handler(sender, instance: Room, action: str, **kwargs):
    """
    Signal Receiver: Requirements of room changed
    """
    # Only signal after change (post_add, post_delete, post_clear) are relevant
    if not action.startswith("post"):
        return

    event = instance.event

    violation_type = ConstraintViolation.ViolationType.REQUIRE_NOT_GIVEN
    new_violations = []

    slots_in_this_room: Iterable[AKSlot] = instance.akslot_set.filter(start__isnull=False)

    # For all slots in this room...
    for slot in slots_in_this_room:
        slot_requirements = slot.ak.requirements.all()
        # ... check if they require a property that the room does not fulfill...
        for requirement in slot_requirements:
            if not requirement in instance.properties.all():
                # ...and create a temporary violation if necessary.
                c = ConstraintViolation(
                    type=violation_type,
                    level=ConstraintViolation.ViolationLevel.VIOLATION,
                    event=event,
                    requirement=requirement,
                    room=instance,
                )
                c.aks_tmp.add(slot.ak)
                c.ak_slots_tmp.add(slot)
                new_violations.append(c)

    # Once this list is constructed use it for updating
    # (removing of obsolete CVs and adding of new ones)
    existing_violations_to_check = list(instance.constraintviolation_set.filter(type=violation_type))
    update_constraint_violations(new_violations, existing_violations_to_check)


@receiver(post_save, sender=Availability)
def availability_changed_handler(sender, instance: Availability, **kwargs):
    """
    Signal receiver: Availalability changed

    Changes might affect: category availability, AK availability, Room availability
    """
    event = instance.event

    # An AK's availability changed: Might affect AK slots scheduled outside the permitted time
    if instance.ak:
        violation_type = ConstraintViolation.ViolationType.SLOT_OUTSIDE_AVAIL
        new_violations = []

        availabilities_of_this_ak: Iterable[Availability] = instance.ak.availabilities.all()
        slots_of_this_ak: Iterable[AKSlot] = instance.ak.akslot_set.filter(start__isnull=False)

        for slot in slots_of_this_ak:
            covered = False
            for availability in availabilities_of_this_ak:
                covered = availability.start <= slot.start and availability.end >= slot.end
                if covered:
                    break
            if not covered:
                c = ConstraintViolation(
                    type=violation_type,
                    level=ConstraintViolation.ViolationLevel.VIOLATION,
                    event=event
                )
                c.aks_tmp.add(instance.ak)
                c.ak_slots_tmp.add(slot)
                new_violations.append(c)

        # ... and compare to/update list of existing violations of this type
        # belonging to the AK that was recently changed (important!)
        existing_violations_to_check = list(instance.ak.constraintviolation_set.filter(type=violation_type))
        # print(existing_violations_to_check)
        update_constraint_violations(new_violations, existing_violations_to_check)


@receiver(post_save, sender=Event)
def event_changed_handler(sender, instance: Event, **kwargs):
    """
    Signal receiver: Event changed

    Changes might affect: Reso deadline
    """
    # Check for reso ak after reso deadline (which might have changed)
    if instance.reso_deadline:
        for slot in instance.akslot_set.filter(start__isnull=False, ak__reso=True):
            update_cv_reso_deadline_for_slot(slot)
    else:
        # No reso deadline, delete all violations
        violation_type = ConstraintViolation.ViolationType.AK_AFTER_RESODEADLINE
        existing_violations_to_check = list(instance.constraintviolation_set.filter(type=violation_type))
        update_constraint_violations([], existing_violations_to_check)
