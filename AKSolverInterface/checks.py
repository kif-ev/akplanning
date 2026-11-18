"""
Checks of the preference data used for automatic scheduling
(see automatic scheduling workflow in :mod:`AKSolverInterface.views`)
"""
from collections import defaultdict
from datetime import timedelta

from AKModel.models import Event
from AKPreference.checks import availability_overlap
from AKPreference.models import AKPreference


def _longest_window_inside_slots(windows, slots) -> timedelta:
    """
    Get the length of the longest part of the given windows that lies completely inside one of the given slots

    In contrast to :meth:`Availability.intersection`, the slots are not merged before,
    i.e., adjacent slots are treated separately.

    :param windows: list of availabilities (time windows)
    :param slots: list of slots (objects with start and end)
    :return: length of the longest part
    """
    longest = timedelta(0)
    for window in windows:
        for slot in slots:
            length = min(window.end, slot.end) - max(window.start, slot.start)
            longest = max(longest, length)
    return longest


def _required_preferences(event: Event):
    """
    Get all preferences of the event that mark a participant as required for an AK with at least one slot
    (preferences for trashed AKs are ignored)
    """
    return (AKPreference.objects
            .filter(event=event, preference=AKPreference.PreferenceLevel.REQUIRED, ak__akslot__isnull=False,
                    ak__trashed_at__isnull=True)
            .distinct()
            .select_related('participant', 'ak', 'ak__category')
            .prefetch_related('ak__akslot_set', 'ak__availabilities', 'participant__availabilities')
            .order_by('participant__name', 'participant__pk', 'ak__name'))


def participants_required_for_too_many_slots(event: Event) -> list[dict]:
    """
    Get all participants that are required for more AK slots than there are default slots

    Since a participant cannot attend multiple slots at the same time, these requirements can probably
    not all be fulfilled (unless multiple slots fit into a single default slot one after another).

    :param event: event to check (should have default slots)
    :return: list of violations, each a dict containing the participant, the list of their required preferences,
        the number of slots of the required AKs and the number of default slots
    :rtype: list[dict]
    """
    default_slot_count = event.defaultslot_set.count()

    preferences_by_participant = defaultdict(list)
    for preference in _required_preferences(event):
        preferences_by_participant[preference.participant].append(preference)

    violations = []
    for participant, preferences in preferences_by_participant.items():
        required_slot_count = sum(len(p.ak.akslot_set.all()) for p in preferences)
        if required_slot_count > default_slot_count:
            violations.append({
                "participant": participant,
                "preferences": preferences,
                "required_slot_count": required_slot_count,
                "default_slot_count": default_slot_count,
            })
    return violations


def required_preferences_without_overlap(event: Event) -> tuple[list[dict], list[dict] | None]:
    """
    Check for every required preference whether the availabilities of the AK and the participant
    overlap long enough to place the longest slot of the AK

    Participants without availabilities are treated as available during the whole event,
    AKs without (valid) availabilities cannot be placed at all (same semantics as for the solver export).

    Two variants are checked:

    * loose: The overlap of AK and participant availabilities contains a window at least as long
      as the longest slot of the AK (see :func:`AKPreference.checks.availability_overlap`,
      the same check is used when participants enter their preferences)
    * strict: Only the parts of the overlap inside default slots intended for the category of the AK are considered,
      one of these parts has to be at least as long as the longest slot of the AK
      (only checked if the event has default slots)

    :param event: event to check
    :return: two lists of violations (loose and strict, the latter is None if there are no default slots),
        each violation is a dict containing the preference, the duration of the longest slot
        and the length of the longest window available for the respective check
    :rtype: tuple[list[dict], list[dict] | None]
    """
    default_slots = list(event.defaultslot_set.prefetch_related('primary_categories'))

    loose_violations = []
    strict_violations = [] if default_slots else None

    for preference in _required_preferences(event):
        ak = preference.ak
        # Required preferences only contain AKs with slots, hence the result is never None here
        result = availability_overlap(event, ak, preference.participant.availabilities.all())

        if not result.sufficient:
            loose_violations.append({
                "preference": preference,
                "longest_slot": result.longest_slot,
                "longest_window": result.longest_overlap,
            })

        if default_slots:
            relevant_slots = [ds for ds in default_slots if ak.category in ds.primary_categories.all()]
            longest_window = _longest_window_inside_slots(result.overlap, relevant_slots)
            if longest_window < result.longest_slot:
                strict_violations.append({
                    "preference": preference,
                    "longest_slot": result.longest_slot,
                    "longest_window": longest_window,
                })

    return loose_violations, strict_violations
