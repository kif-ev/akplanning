"""
Preparation of the data for the ID lookup step of the automatic scheduling workflow

Allows to look up the objects behind the IDs used in the solver export and the solver output
without any API calls: All necessary information is serialized here and embedded into the page.

Each object is represented as a dict with the keys

* ``title``: string representation
* ``fields``: list of ``[label, value]`` pairs, values are either strings or lists of references to other objects
  that can be looked up as well (dicts with ``type``, ``id`` and ``label``)
* ``links``: list of dicts with ``text`` and ``url`` (frontend detail views and admin edit views)
"""
from django.apps import apps
from django.db.models import Prefetch
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from AKModel.models import AKSlot, Event


def _ref(obj_type: str, pk, label) -> dict:
    """Reference to another object that can be looked up"""
    return {"type": obj_type, "id": str(pk), "label": str(label)}


def _admin_link(text, url_name: str, pk) -> dict:
    """Link to the admin change view of an object"""
    return {"text": str(text), "url": reverse(url_name, args=[pk])}


def _format_range(event: Event, start, end) -> str:
    """Format a time range in the timezone of the event (localized according to the active language)"""
    start = start.astimezone(event.timezone)
    end = end.astimezone(event.timezone)
    end_format = 'G:i' if start.date() == end.date() else 'D G:i'
    return f"{date_format(start, 'D G:i', use_l10n=True)} - {date_format(end, end_format, use_l10n=True)}"


def _yes_no(value: bool) -> str:
    return _("Yes") if value else _("No")


def lookup_aks(event: Event) -> dict:
    """Serialize all AKs of the event (export: ``info.django_ak_id`` of the AK slots)"""
    aks = {}
    for ak in event.ak_set.select_related('category', 'track').prefetch_related('owners', 'akslot_set'):
        links = []
        if apps.is_installed("AKSubmission"):
            links.append({"text": _("Frontend"), "url": str(ak.detail_url)})
        links.append(_admin_link(_("Edit in admin"), "admin:AKModel_ak_change", ak.pk))
        aks[str(ak.pk)] = {
            "title": ak.name,
            "fields": [
                [_("Short name"), ak.short_name or "-"],
                [_("Category"), str(ak.category)],
                [_("Track"), str(ak.track) if ak.track else "-"],
                [_("Owners"), ", ".join(str(owner) for owner in ak.owners.all()) or "-"],
                [_("Slots"), [_ref("slot", slot.pk, f"#{slot.pk} ({slot.duration} h)")
                              for slot in ak.akslot_set.all()]],
            ],
            "links": links,
        }
    return aks


def lookup_slots(event: Event) -> dict:
    """Serialize all AK slots of the event (export: ``id`` of the AK slots, also used in conflicts,
    dependencies and preferences)"""
    slots = {}
    for slot in AKSlot.objects.filter(event=event).select_related('ak', 'room', 'event'):
        links = []
        if apps.is_installed("AKSubmission"):
            links.append({"text": _("AK in frontend"), "url": str(slot.ak.detail_url)})
        links.append(_admin_link(_("Edit in admin"), "admin:AKModel_akslot_change", slot.pk))
        slots[str(slot.pk)] = {
            "title": f"{slot.ak.name} (#{slot.pk})",
            "fields": [
                [_("AK"), [_ref("ak", slot.ak.pk, slot.ak.name)]],
                [_("Duration"), f"{slot.duration} h"],
                [_("Scheduled"), _format_range(event, slot.start, slot.end) if slot.start else _("Not scheduled yet")],
                [_("Room"), [_ref("room", slot.room.pk, slot.room)] if slot.room else "-"],
                [_("Fixed"), _yes_no(slot.fixed)],
            ],
            "links": links,
        }
    return slots


def lookup_rooms(event: Event) -> dict:
    """Serialize all rooms of the event (export: ``id`` of the rooms)"""
    rooms = {}
    for room in event.rooms.prefetch_related('properties'):
        links = []
        if apps.is_installed("AKPlan"):
            links.append({"text": _("Plan of this room"),
                          "url": reverse("plan:plan_room", kwargs={"event_slug": event.slug, "pk": room.pk})})
        links.append(_admin_link(_("Edit in admin"), "admin:AKModel_room_change", room.pk))
        rooms[str(room.pk)] = {
            "title": str(room),
            "fields": [
                [_("Location"), room.location or "-"],
                [_("Capacity"), str(room.capacity)],
                [_("Properties"), ", ".join(str(p) for p in room.properties.all()) or "-"],
            ],
            "links": links,
        }
    return rooms


def lookup_timeslots(event: Event) -> dict:
    """
    Serialize all timeslots of the discretization used in the export
    (export: ``id`` of the timeslots in the blocks, solver output: ``timeslot_ids``)

    The timeslots are linked to the default slots containing them.

    :raises ValueError: if the timeslots cannot be generated (e.g., because of partially overlapping default slots)
    """
    default_slots = list(event.defaultslot_set.prefetch_related('primary_categories').order_by('start'))
    timeslots = {}
    for block_idx, block in enumerate(event.discretize_timeslots()):
        if not block:
            continue
        for timeslot in block:
            containing = [ds for ds in default_slots
                          if ds.start <= timeslot.avail.start and timeslot.avail.end <= ds.end]
            fields = [
                [_("Time"), _format_range(event, timeslot.avail.start, timeslot.avail.end)],
                [_("Block"), f"{block_idx} ({_format_range(event, block[0].avail.start, block[-1].avail.end)})"],
            ]
            if default_slots:
                fields.append([_("Default slot"), "; ".join(
                        f"{_format_range(event, ds.start, ds.end)} "
                        f"({', '.join(str(c) for c in ds.primary_categories.all()) or _('No categories')})"
                        for ds in containing) or "-"])
            timeslots[str(timeslot.idx)] = {
                "title": _("Timeslot {id}").format(id=timeslot.idx),
                "fields": fields,
                "links": [_admin_link(_("Default slot {time}").format(time=_format_range(event, ds.start, ds.end)),
                                      "admin:AKModel_defaultslot_change", ds.pk) for ds in containing],
            }
    return timeslots


def lookup_participants(event: Event) -> dict:
    """
    Serialize all participants of the event (export: ``id`` of the participants)

    Includes the dummy participants generated for the AK owners during export
    (see :class:`AKSolverInterface.serializers.ExportParticipantAndDummiesSerializer`).
    Their IDs are computed in the same way. Dummy participants of owners linked to a participant
    are not exported if that participant is exported (i.e., if preferences are exported and the participant
    is not filtered out), but are always included here since the lookup does not know the export settings.
    """
    participants = {}
    next_participant_pk = 1
    linked_owner_pks = set()

    if apps.is_installed("AKPreference"):
        # pylint: disable=import-outside-toplevel
        from AKPreference.models import AKPreference, EventParticipant

        # Ignore preferences for trashed AKs and AKs owned by the participant (as in the export)
        active_preferences = (AKPreference.objects.filter(ak__trashed_at__isnull=True)
                              .exclude(AKPreference.for_owned_ak()).select_related('ak'))
        for participant in event.participants.prefetch_related(
                Prefetch('akpreference_set', queryset=active_preferences), 'requirements').select_related('ak_owner'):
            preferences = list(participant.akpreference_set.all())
            required = [p.ak for p in preferences if p.required]
            if participant.ak_owner_id is not None:
                linked_owner_pks.add(participant.ak_owner_id)
            fields = [
                [_("Preferences"), str(len(preferences))],
                [_("AK owner"), str(participant.ak_owner) if participant.ak_owner else "-"],
            ]
            # 'Required' can no longer be selected, so only show it for participants that still have such preferences
            if required:
                fields.append([_("Required for"), [_ref("ak", ak.pk, ak.name) for ak in required]])
            fields.append([_("Requirements"), ", ".join(str(r) for r in participant.requirements.all()) or "-"])
            participants[str(participant.pk)] = {
                "title": str(participant),
                "fields": fields,
                "links": [_admin_link(_("Edit in admin"), "admin:AKPreference_eventparticipant_change",
                                      participant.pk)],
            }
        if EventParticipant.objects.exists():
            next_participant_pk = EventParticipant.objects.latest("pk").pk + 1

    # Dummy participants for AK owners (same numbering as in the export)
    for new_pk, owner in enumerate(event.owners, next_participant_pk):
        owned_aks = list(event.ak_set.filter(owners=owner, akslot__isnull=False).distinct())
        if not owned_aks:
            continue
        fields = [[_("AKs"), [_ref("ak", ak.pk, ak.name) for ak in owned_aks]]]
        if owner.pk in linked_owner_pks:
            fields.append([_("Note"), _("Not exported if a participant linked to this AK owner is exported "
                                        "(with the preferences)")])
        participants[str(new_pk)] = {
            "title": _("{owner} [AK owner, dummy participant]").format(owner=owner),
            "fields": fields,
            "links": [
                _admin_link(_("Edit AK owner in admin"), "admin:AKModel_akowner_change", owner.pk),
                {"text": _("AKs of this owner"),
                 "url": reverse("admin:aks_by_owner", kwargs={"event_slug": event.slug, "pk": owner.pk})},
            ],
        }
    return participants
