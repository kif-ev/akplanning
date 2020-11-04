from django.db.models.signals import post_save
from django.dispatch import receiver

from AKModel.availability.models import Availability
from AKModel.models import AK, AKSlot, Room, Event, AKOwner, ConstraintViolation


@receiver(post_save, sender=AK)
def ak_changed_handler(sender, instance: AK, **kwargs):
    # Changes might affect: Owner(s), Requirements, Conflicts, Prerequisites, Category, Interest
    print(f"{instance} changed")

    event = instance.event

    # Owner might have changed: Might affect multiple AKs by the same owner at the same time
    conflicts = []
    type = ConstraintViolation.ViolationType.OWNER_TWO_SLOTS
    # For all owners...
    for owner in instance.owners.all():
        # ...find overlapping AKs...
        slots_by_owner : [AKSlot] = []
        slots_by_owner_this_ak : [AKSlot] = []
        aks_by_owner = owner.ak_set.all()
        for ak in aks_by_owner:
            if ak != instance:
                slots_by_owner.extend(ak.akslot_set.filter(start__isnull=False))
            else:
                # ToDo Fill this outside of loop?
                slots_by_owner_this_ak.extend(ak.akslot_set.filter(start__isnull=False))
        for slot in slots_by_owner_this_ak:
            for other_slot in slots_by_owner:
                if slot.overlaps(other_slot):
                    # TODO Create ConstraintViolation here
                    c = ConstraintViolation(
                        type=type,
                        level=ConstraintViolation.ViolationLevel.VIOLATION,
                        event=event,
                        ak_owner=owner
                    )
                    c.aks_tmp.add(instance)
                    c.aks_tmp.add(other_slot.ak)
                    c.ak_slots_tmp.add(slot)
                    c.ak_slots_tmp.add(other_slot)
                    conflicts.append(c)
        print(f"{owner} has the following conflicts: {conflicts}")
    # ... and compare to/update list of existing violations of this type:
    current_violations = instance.constraintviolation_set.filter(type=type)
    for conflict in conflicts:
        pass
        # TODO Remove from list of current_violations if an equal new one is found
        # TODO Otherwise, store this conflict in db
    # TODO Remove all violations still in current_violations


@receiver(post_save, sender=AKSlot)
def akslot_changed_handler(sender, instance, **kwargs):
    # Changes might affect: Duplicate parallel, Two in room
    print(f"{sender} changed")
    # TODO Replace with real handling


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
