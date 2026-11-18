"""
Checks whether participants required for an AK are available long enough at the same time as the AK can take place

Used both when participants enter their preferences (see :class:`AKPreference.forms.PreferenceFormSet`)
and in the automatic scheduling workflow (see :mod:`AKSolverInterface.checks`).
"""
from dataclasses import dataclass, field
from datetime import timedelta

from AKModel.availability.models import Availability
from AKModel.models import AK, Event


def valid_availabilities(availabilities) -> list[Availability]:
    """
    Filter out invalid availabilities (end not after start, could be created by older versions of the form)
    """
    return [a for a in availabilities if a.end > a.start]


def longest_availability(availabilities) -> timedelta:
    """
    Get the length of the longest of the given availabilities (0 if there are none)
    """
    return max((a.end - a.start for a in availabilities), default=timedelta(0))


@dataclass
class AvailabilityOverlap:
    """
    Result of the overlap check of an AK and a participant
    """
    longest_slot: timedelta
    """Duration of the longest slot of the AK"""
    overlap: list[Availability] = field(default_factory=list)
    """Time windows in which both the AK can take place and the participant is available"""

    @property
    def longest_overlap(self) -> timedelta:
        """Length of the longest window in which both the AK can take place and the participant is available"""
        return longest_availability(self.overlap)

    @property
    def sufficient(self) -> bool:
        """Whether the longest slot of the AK fits into the overlap (loose check)"""
        return self.longest_overlap >= self.longest_slot


def availability_overlap(event: Event, ak: AK, participant_availabilities) -> AvailabilityOverlap | None:
    """
    Compute the overlap of the availabilities of an AK and a participant (loose check:
    the overlap has to contain a window at least as long as the longest slot of the AK)

    Participants without availabilities are treated as available during the whole event,
    AKs without (valid) availabilities cannot take place at all (same semantics as for the solver export).

    :param event: event the AK belongs to
    :param ak: AK to check (should have prefetched slots and availabilities if called for many AKs)
    :param participant_availabilities: availabilities of the participant
    :return: overlap information or None if the AK has no slots (and hence does not need to be checked)
    :rtype: AvailabilityOverlap | None
    """
    slots = list(ak.akslot_set.all())
    if not slots:
        return None
    longest_slot = timedelta(hours=float(max(slot.duration for slot in slots)))

    ak_availabilities = valid_availabilities(ak.availabilities.all())
    participant_availabilities = (valid_availabilities(participant_availabilities)
                                  or [Availability(event=event, start=event.start, end=event.end)])
    return AvailabilityOverlap(
            longest_slot=longest_slot,
            overlap=Availability.intersection(ak_availabilities, participant_availabilities),
    )
