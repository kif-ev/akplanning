import itertools
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Generator, Iterable

from django.apps import apps
from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.db.models import Count
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords
from timezone_field import TimeZoneField

# Custom validators to be used for some of the fields
# Prevent inclusion of the quotation marks ' " ´ `
# This may be necessary to prevent javascript issues
no_quotation_marks_validator = RegexValidator(regex=r"['\"´`]+", inverse_match=True,
                                              message=_('May not contain quotation marks'))
# Enforce that the field contains of at least one letter or digit (and not just special characters
# This prevents issues when autogenerating slugs from that field
slugable_validator = RegexValidator(regex=r"[\w\s]+", message=_('Must contain at least one letter or digit'))


@dataclass
class OptimizerTimeslot:
    """Class describing a discrete timeslot. Used to interface with an optimizer."""

    avail: "Availability"
    """The availability object corresponding to this timeslot."""

    idx: int
    """The unique index of this optimizer timeslot."""

    constraints: set[str]
    """The set of time constraints fulfilled by this object."""

    def merge(self, other: "OptimizerTimeslot") -> "OptimizerTimeslot":
        """Merge with other OptimizerTimeslot.

        Creates a new OptimizerTimeslot object.
        Its availability is constructed by merging the availabilities of self and other,
        its constraints by taking the union of both constraint sets.
        As an index, the index of self is used.
        """
        avail = self.avail.merge_with(other.avail)
        constraints = self.constraints.union(other.constraints)
        return OptimizerTimeslot(
            avail=avail, idx=self.idx, constraints=constraints
        )

    def __repr__(self) -> str:
        return f"({self.avail.simplified}, {self.idx}, {self.constraints})"

TimeslotBlock = list[OptimizerTimeslot]


def merge_blocks(
    blocks: Iterable[TimeslotBlock]
) -> Iterable[TimeslotBlock]:
    """Merge iterable of blocks together.

    The timeslots of all blocks are grouped into maximal blocks.
    Timeslots with the same start and end are identified with each other
    and merged (cf `OptimizerTimeslot.merge`).
    Throws a ValueError if any timeslots are overlapping but do not
    share the same start and end, i.e. partial overlap is not allowed.

    :param blocks: iterable of blocks to merge.
    :return: iterable of merged blocks.
    :rtype: iterable over lists of OptimizerTimeslot objects
    """
    if not blocks:
        return []

    # flatten timeslot iterables to single chain
    timeslot_chain = itertools.chain.from_iterable(blocks)

    # sort timeslots according to start
    timeslots = sorted(
        timeslot_chain,
        key=lambda slot: slot.avail.start
    )

    if not timeslots:
        return []

    all_blocks = []
    current_block = [timeslots[0]]
    timeslots = timeslots[1:]

    for slot in timeslots:
        if current_block and slot.avail.overlaps(current_block[-1].avail, strict=True):
            if (
                slot.avail.start == current_block[-1].avail.start
                and slot.avail.end == current_block[-1].avail.end
            ):
                # the same timeslot -> merge
                current_block[-1] = current_block[-1].merge(slot)
            else:
                # partial overlap of interiors -> not supported
                raise ValueError(
                    "Partially overlapping timeslots are not supported!"
                    f" ({current_block[-1].avail.simplified}, {slot.avail.simplified})"
                )
        elif not current_block or slot.avail.overlaps(current_block[-1].avail, strict=False):
            # only endpoints in intersection -> same block
            current_block.append(slot)
        else:
            # no overlap at all -> new block
            all_blocks.append(current_block)
            current_block = [slot]

    if current_block:
        all_blocks.append(current_block)

    return all_blocks


class Event(models.Model):
    """
    An event supplies the frame for all Aks.
    """
    name = models.CharField(max_length=64, unique=True, verbose_name=_('Name'),
                            help_text=_('Name or iteration of the event'))
    slug = models.SlugField(max_length=32, unique=True, verbose_name=_('Short Form'),
                            help_text=_('Short name of letters/numbers/dots/dashes/underscores used in URLs.'))

    place = models.CharField(max_length=128, blank=True, verbose_name=_('Place'),
                             help_text=_('City etc. the event takes place in'))
    timezone = TimeZoneField(default='Europe/Berlin', blank=False, choices_display="WITH_GMT_OFFSET",
                             verbose_name=_('Time Zone'), help_text=_('Time Zone where this event takes place in'))
    start = models.DateTimeField(verbose_name=_('Start'), help_text=_('Time the event begins'))
    end = models.DateTimeField(verbose_name=_('End'), help_text=_('Time the event ends'))
    reso_deadline = models.DateTimeField(verbose_name=_('Resolution Deadline'), blank=True, null=True,
                                         help_text=_('When should AKs with intention to submit a resolution be done?'))

    interest_start = models.DateTimeField(verbose_name=_('Interest Window Start'), blank=True, null=True,
                                          help_text=
                                          _('Opening time for expression of interest. When left blank, no interest '
                                            'indication will be possible.'))

    interest_end = models.DateTimeField(verbose_name=_('Interest Window End'), blank=True, null=True,
                                        help_text=_('Closing time for expression of interest.'))

    public = models.BooleanField(verbose_name=_('Public event'), default=True,
                                 help_text=_('Show this event on overview page.'))

    active = models.BooleanField(verbose_name=_('Active State'), help_text=_('Marks currently active events'))
    plan_hidden = models.BooleanField(verbose_name=_('Plan Hidden'), help_text=_('Hides plan for non-staff users'),
                                      default=True)
    plan_published_at = models.DateTimeField(verbose_name=_('Plan published at'), blank=True, null=True,
                                             help_text=_('Timestamp at which the plan was published'))

    poll_hidden = models.BooleanField(verbose_name=_('Poll Hidden'),
                                      help_text=_('Hides preference poll for non-staff users'),
                                      default=True)
    poll_published_at = models.DateTimeField(verbose_name=_('Poll published at'), blank=True, null=True,
                                             help_text=_('Timestamp at which the preference poll was published'))

    base_url = models.URLField(verbose_name=_("Base URL"), help_text=_("Prefix for wiki link construction"), blank=True)
    wiki_export_template_name = models.CharField(verbose_name=_("Wiki Export Template Name"), blank=True, max_length=50)
    default_slot = models.DecimalField(max_digits=4, decimal_places=2, default=2, verbose_name=_('Default Slot Length'),
                                       help_text=_('Default length in hours that is assumed for AKs in this event.'))
    export_slot = models.DecimalField(max_digits=4, decimal_places=2, default=1, verbose_name=_('Export Slot Length'),
                                        help_text=_(
                                            'Slot duration in hours that is used in the timeslot discretization, '
                                            'when this event is exported for the solver.'
                                        ))


    contact_email = models.EmailField(verbose_name=_("Contact email address"), blank=True,
                                      help_text=_("An email address that is displayed on every page "
                                                  "and can be used for all kinds of questions"))

    class Meta:
        verbose_name = _('Event')
        verbose_name_plural = _('Events')
        ordering = ['-start']

    def __str__(self):
        return self.name

    @staticmethod
    def get_by_slug(slug):
        """
        Get event by its slug

        :param slug: slug of the event
        :return: event identified by the slug
        :rtype: Event
        """
        return Event.objects.get(slug=slug)

    @staticmethod
    def get_next_active():
        """
        Get first active event taking place
        :return: matching event (if any) or None
        :rtype: Event
        """
        event = Event.objects.filter(active=True).order_by('start').first()
        # No active event? Return the next event taking place
        if event is None:
            event = Event.objects.order_by('start').filter(start__gt=datetime.now().astimezone()).first()
        return event

    def get_categories_with_aks(self, wishes_seperately=False,
                                filter_func=lambda ak: True, hide_empty_categories=False,
                                types=None, types_all_selected_only=False):
        """
        Get AKCategories as well as a list of AKs belonging to the category for this event

        :param wishes_seperately: Return wishes as individual list.
        :type wishes_seperately: bool
        :param filter_func: Optional filter predicate, only include AK in list if filter returns True
        :type filter_func: (AK)->bool
        :param hide_empty_categories: If True, categories with no AKs will not be included in the result
        :type hide_empty_categories: bool
        :param types: Optional list of AK types to filter by, if None, all types are included
        :type types: list[AKType] | None
        :param types_all_selected_only: If True, only include AKs that have all of the selected types at the same time
        :type types_all_selected_only: bool
        :return: list of category-AK-list-tuples, optionally the additional list of AK wishes
        :rtype: list[(AKCategory, list[AK])] [, list[AK]]
        """
        categories = self.akcategory_set.select_related('event').all()
        categories_with_aks = []
        ak_wishes = []

        # Fill lists by iterating
        # A different behavior is needed depending on whether wishes should show up inside their categories
        # or as a separate category

        def _get_category_aks(category, types):
            """
            Get all AKs belonging to a category
            Use joining and prefetching to reduce the number of necessary SQL queries

            :param category: category the AKs should belong to
            :return: QuerySet over AKs
            :return: QuerySet[AK]
            """
            s = category.ak_set
            if types is not None:
                s = s.filter(types__in=types).distinct()
                if types_all_selected_only:
                    # TODO fix - this only works in very specific cases
                    s = s.annotate(Count('types')).filter(types__count=len(types))
            return s.select_related('event').prefetch_related('owners', 'akslot_set', 'types').all()

        if wishes_seperately:
            for category in categories:
                ak_list = []
                for ak in _get_category_aks(category, types):
                    if filter_func(ak):
                        if ak.wish:
                            ak_wishes.append(ak)
                        else:
                            ak_list.append(ak)
                if not hide_empty_categories or len(ak_list) > 0:
                    categories_with_aks.append((category, ak_list))
            return categories_with_aks, ak_wishes

        for category in categories:
            ak_list = []
            for ak in _get_category_aks(category, types):
                if filter_func(ak):
                    ak_list.append(ak)
            if not hide_empty_categories or len(ak_list) > 0:
                categories_with_aks.append((category, ak_list))
        return categories_with_aks

    def get_unscheduled_wish_slots(self):
        """
        Get all slots of wishes that are currently not scheduled
        :return: queryset of theses slots
        :rtype: QuerySet[AKSlot]
        """
        return self.akslot_set.filter(start__isnull=True).annotate(Count('ak__owners')).filter(ak__owners__count=0)

    def get_aks_without_availabilities(self):
        """
        Gt all AKs that don't have any availability at all

        :return: generator over these AKs
        :rtype: Generator[AK]
        """
        return (self.ak_set
                .annotate(Count('availabilities', distinct=True))
                .annotate(Count('owners', distinct=True))
                .filter(availabilities__count=0, owners__count__gt=0)
                )

    def _generate_slots_from_block(
        self,
        start: datetime,
        end: datetime,
        slot_duration: timedelta,
        *,
        slot_index: int = 0,
        constraints: set[str] | None = None,
    ) -> Generator[TimeslotBlock, None, int]:
        """Discretize a time range into timeslots.

        Uses a uniform discretization into discrete slots of length `slot_duration`,
        starting at `start`. No incomplete timeslots are generated, i.e.
        if (`end` - `start`) is not a whole number multiple of `slot_duration`
        then the last incomplete timeslot is dropped.

        :param start: Start of the time range.
        :param end: Start of the time range.
        :param slot_duration: Duration of a single timeslot in the discretization.
        :param slot_index: index of the first timeslot. Defaults to 0.

        :yield: Block of optimizer timeslots as the discretization result.
        :ytype: list of OptimizerTimeslot

        :return: The first slot index after the yielded blocks, i.e.
            `slot_index` + total # generated timeslots
        :rtype: int
        """
        # local import to prevent cyclic import
        # pylint: disable=import-outside-toplevel
        from AKModel.availability.models import Availability

        current_slot_start = start
        previous_slot_start: datetime | None = None

        if constraints is None:
            constraints = set()

        current_block = []

        room_availabilities = list({
            availability
            for room in Room.objects.filter(event=self)
            for availability in room.availabilities.all()
        })

        while current_slot_start + slot_duration <= end:
            slot = Availability(
                event=self,
                start=current_slot_start,
                end=current_slot_start + slot_duration,
            )

            if any((availability.contains(slot) for availability in room_availabilities)):
                # no gap in a block
                if (
                    previous_slot_start is not None
                    and previous_slot_start + slot_duration < current_slot_start
                ):
                    yield current_block
                    current_block = []

                current_block.append(
                    OptimizerTimeslot(avail=slot, idx=slot_index, constraints=constraints)
                )
                previous_slot_start = current_slot_start

            slot_index += 1
            current_slot_start += slot_duration

        if current_block:
            yield current_block

        return slot_index

    def uniform_time_slots(self, *, slots_in_an_hour: float) -> Iterable[TimeslotBlock]:
        """Uniformly discretize the entire event into blocks of timeslots.

        Discretizes entire event uniformly. May not necessarily result in a single block
        as slots with no room availability are dropped.

        :param slots_in_an_hour: The percentage of an hour covered by a single slot.
            Determines the discretization granularity.
        :yield: Block of optimizer timeslots as the discretization result.
        :ytype: list of OptimizerTimeslot
        """
        all_category_constraints = AKCategory.create_category_optimizer_constraints(
            AKCategory.objects.filter(event=self).all()
        )

        yield from self._generate_slots_from_block(
            start=self.start,
            end=self.end,
            slot_duration=timedelta(hours=1.0 / slots_in_an_hour),
            constraints=all_category_constraints,
        )

    def default_time_slots(self, *, slots_in_an_hour: float) -> Iterable[TimeslotBlock]:
        """Discretize all default slots into blocks of timeslots.

        In the discretization each default slot corresponds to one block.

        :param slots_in_an_hour: The percentage of an hour covered by a single slot.
            Determines the discretization granularity.
        :yield: Block of optimizer timeslots as the discretization result.
        :ytype: list of TimeslotBlock
        """
        slot_duration = timedelta(hours=1.0 / slots_in_an_hour)
        slot_index = 0

        for block_slot in DefaultSlot.objects.filter(event=self).order_by("start", "end"):
            category_constraints = AKCategory.create_category_optimizer_constraints(
                block_slot.primary_categories.all()
            )

            slot_index = yield from self._generate_slots_from_block(
                start=block_slot.start,
                end=block_slot.end,
                slot_duration=slot_duration,
                slot_index=slot_index,
                constraints=category_constraints,
            )

    def discretize_timeslots(self, *, slots_in_an_hour: float | None = None) -> Iterable[TimeslotBlock]:
        """"Choose discretization scheme.

        Uses default_time_slots if the event has any DefaultSlot, otherwise uniform_time_slots.

        :param slots_in_an_hour: The percentage of an hour covered by a single slot.
            Determines the discretization granularity.
        :yield: Block of optimizer timeslots as the discretization result.
        :ytype: list of TimeslotBlock
        """

        if slots_in_an_hour is None:
            slots_in_an_hour = 1.0 / float(self.export_slot)

        if DefaultSlot.objects.filter(event=self).exists():
            # discretize default slots if they exists
            yield from merge_blocks(self.default_time_slots(slots_in_an_hour=slots_in_an_hour))
        else:
            yield from self.uniform_time_slots(slots_in_an_hour=slots_in_an_hour)

    @transaction.atomic
    def schedule_from_json(
        self, schedule: str | dict[str, Any], *, check_for_data_inconsistency: bool = True
    ) -> int:
        """Load AK schedule from a json string.

        :param schedule: A string that can be decoded to json, describing
            the AK schedule. The json data is assumed to be constructed
            following the output specification of the KoMa conference optimizer, cf.
            https://github.com/Die-KoMa/ak-plan-optimierung/wiki/Input-&-output-format
        """
        if isinstance(schedule, str):
            schedule = json.loads(schedule)

        if "input" not in schedule or "scheduled_aks" not in schedule:
            raise ValueError(_("Cannot parse malformed JSON input."))

        if apps.is_installed("AKSolverInterface") and check_for_data_inconsistency:
            from AKSolverInterface.serializers import ExportEventSerializer   # pylint: disable=import-outside-toplevel
            export_dict = ExportEventSerializer(self).data

            if schedule["input"] != export_dict:
                raise ValueError(_("Data has changed since the export. Reexport and run the solver again."))

        slots_in_an_hour = 1.0 / schedule["input"]["timeslots"]["info"]["duration"]

        timeslot_dict = {
            timeslot.idx: timeslot
            for block in self.discretize_timeslots(slots_in_an_hour=slots_in_an_hour)
            for timeslot in block
        }

        slots_updated = 0
        for scheduled_slot in schedule["scheduled_aks"]:
            scheduled_slot["timeslot_ids"] = list(map(int, scheduled_slot["timeslot_ids"]))
            slot = AKSlot.objects.get(id=int(scheduled_slot["ak_id"]))

            if not scheduled_slot["timeslot_ids"]:
                raise ValueError(
                    _("AK {ak_name} is not assigned any timeslot by the solver").format(ak_name=slot.ak.name)
                )

            start_timeslot = timeslot_dict[min(scheduled_slot["timeslot_ids"])].avail
            end_timeslot = timeslot_dict[max(scheduled_slot["timeslot_ids"])].avail
            solver_duration = (end_timeslot.end - start_timeslot.start).total_seconds() / 3600.0

            if solver_duration + 2e-4 < slot.duration:
                raise ValueError(
                    _(
                        "Duration of AK {ak_name} assigned by solver ({solver_duration} hours) "
                        "is less than the duration required by the slot ({slot_duration} hours)"
                    ).format(
                        ak_name=slot.ak.name,
                        solver_duration=solver_duration,
                        slot_duration=slot.duration,
                    )
                )

            if slot.fixed:
                solver_room = Room.objects.get(id=int(scheduled_slot["room_id"]))
                if slot.room != solver_room:
                    raise ValueError(
                        _(
                            "Fixed AK {ak_name} assigned by solver to room {solver_room} "
                            "is fixed to room {slot_room}"
                        ).format(
                            ak_name=slot.ak.name,
                            solver_room=solver_room.name,
                            slot_room=slot.room.name,
                        )
                    )
                if slot.start != start_timeslot.start:
                    raise ValueError(
                        _(
                            "Fixed AK {ak_name} assigned by solver to start at {solver_start} "
                            "is fixed to start at {slot_start}"
                        ).format(
                            ak_name=slot.ak.name,
                            solver_start=start_timeslot.start,
                            slot_start=slot.start,
                        )
                    )
            else:
                slot.room = Room.objects.get(id=int(scheduled_slot["room_id"]))
                slot.start = start_timeslot.start
                slot.save()
                slots_updated += 1

        return slots_updated

    @property
    def rooms(self):
        """Ordered queryset of all rooms associated to this event."""
        return Room.objects.filter(event=self).order_by()

    @property
    def slots(self):
        """Ordered queryset of all AKSlots associated to this event."""
        return AKSlot.objects.filter(event=self).order_by()

    @property
    def participants(self):
        """Ordered queryset of all participants associated to this event."""
        if apps.is_installed("AKPreference"):
            # local import to prevent cyclic import
            # pylint: disable=import-outside-toplevel
            from AKPreference.models import EventParticipant
            return EventParticipant.objects.filter(event=self).order_by()
        return []

    @property
    def owners(self):
        """Ordered queryset of all AK owners associated to this event."""
        return AKOwner.objects.filter(event=self).order_by()


class AKOwner(models.Model):
    """ An AKOwner describes the person organizing/holding an AK.
    """
    name = models.CharField(max_length=64, verbose_name=_('Nickname'),
                            validators=[no_quotation_marks_validator, slugable_validator],
                            help_text=_('Name to identify an AK owner by'))
    slug = models.SlugField(max_length=64, blank=True, verbose_name=_('Slug'), help_text=_('Slug for URL generation'))
    institution = models.CharField(max_length=128, blank=True, verbose_name=_('Institution'), help_text=_('Uni etc.'))
    link = models.URLField(blank=True, verbose_name=_('Web Link'), help_text=_('Link to Homepage'))

    event = models.ForeignKey(to=Event, on_delete=models.CASCADE, verbose_name=_('Event'),
                              help_text=_('Associated event'))

    class Meta:
        verbose_name = _('AK Owner')
        verbose_name_plural = _('AK Owners')
        ordering = ['name']
        unique_together = [['event', 'name', 'institution'], ['event', 'slug']]

    def __str__(self):
        if self.institution:
            return f"{self.name} ({self.institution})"
        return self.name

    def _generate_slug(self):
        """
        Auto-generate a slug for an owner
        This will start with a very simple slug (the name truncated to a maximum length) and then gradually produce
        more complicated slugs when the previous candidates are already used

        :return: the slug
        :rtype: str
        """
        max_length = self._meta.get_field('slug').max_length

        # Try name alone (truncated if necessary)
        slug_candidate = slugify(self.name)[:max_length]
        if not AKOwner.objects.filter(event=self.event, slug=slug_candidate).exists():
            self.slug = slug_candidate
            return

        # Try name and institution separated by '_' (truncated if necessary)
        slug_candidate = slugify(slug_candidate + '_' + self.institution)[:max_length]
        if not AKOwner.objects.filter(event=self.event, slug=slug_candidate).exists():
            self.slug = slug_candidate
            return

        # Try name + institution + an incrementing digit
        for i in itertools.count(1):
            if not AKOwner.objects.filter(event=self.event, slug=slug_candidate).exists():
                break
            digits = len(str(i))
            slug_candidate = f'{slug_candidate[:-(digits + 1)]}-{i}'

        self.slug = slug_candidate

    def save(self, *args, **kwargs):
        if not self.slug:
            self._generate_slug()

        super().save(*args, **kwargs)

    @staticmethod
    def get_by_slug(event, slug):
        """
        Get owner by slug
        Will be identified by the combination of event slug and owner slug which is unique

        :param event: event
        :param slug: slug of the owner
        :return: owner identified by slugs
        :rtype: AKOwner
        """
        return AKOwner.objects.get(event=event, slug=slug)


class AKCategory(models.Model):
    """ An AKCategory describes the characteristics of an AK, e.g. content vs. recreational.
    """
    name = models.CharField(max_length=64, verbose_name=_('Name'), help_text=_('Name of the AK Category'))
    color = models.CharField(max_length=7, blank=True, verbose_name=_('Color'), help_text=_('Color for displaying'))
    description = models.TextField(blank=True, verbose_name=_("Description"),
                                   help_text=_("Short description of this AK Category"))
    present_by_default = models.BooleanField(blank=True, default=True, verbose_name=_("Present by default"),
                                             help_text=_("Present AKs of this category by default if AK owner did not "
                                                         "specify whether this AK should be presented?"))

    event = models.ForeignKey(to=Event, on_delete=models.CASCADE, verbose_name=_('Event'),
                              help_text=_('Associated event'))

    class Meta:
        verbose_name = _('AK Category')
        verbose_name_plural = _('AK Categories')
        ordering = ['name']
        unique_together = ['event', 'name']

    def __str__(self):
        return self.name

    @staticmethod
    def create_category_optimizer_constraints(categories: Iterable["AKCategory"]) -> set[str]:
        """Create a set of constraint strings from an AKCategory iterable.

        :param categories: The iterable of categories to derive the constraint strings from.
        :return: A set of category constraint strings, i.e. strings of the form
            'availability-cat-<cat.name>'.
        :rtype: set of strings.
        """
        return {
            f"availability-cat-{cat.name}"
            for cat in categories
        }


class AKTrack(models.Model):
    """ An AKTrack describes a set of semantically related AKs.
    """
    name = models.CharField(max_length=64, verbose_name=_('Name'), help_text=_('Name of the AK Track'))
    color = models.CharField(max_length=7, blank=True, verbose_name=_('Color'), help_text=_('Color for displaying'))

    event = models.ForeignKey(to=Event, on_delete=models.CASCADE, verbose_name=_('Event'),
                              help_text=_('Associated event'))

    class Meta:
        verbose_name = _('AK Track')
        verbose_name_plural = _('AK Tracks')
        ordering = ['name']
        unique_together = ['event', 'name']

    def __str__(self):
        return self.name

    def aks_with_category(self):
        """
        Get all AKs that belong to this track with category already joined to prevent additional SQL queries
        :return: queryset over the AKs
        :rtype: QuerySet[AK]
        """
        return self.ak_set.select_related('category').all()


class AKRequirement(models.Model):
    """ An AKRequirement describes something needed to hold an AK, e.g. infrastructure.
    """
    name = models.CharField(max_length=128, verbose_name=_('Name'), help_text=_('Name of the Requirement'))
    relevant_for_participants = models.BooleanField(default=False, verbose_name=_('Relevant for Participants?'),
                                    help_text=_('Show this requirement when collecting participant preferences'))

    event = models.ForeignKey(to=Event, on_delete=models.CASCADE, verbose_name=_('Event'),
                              help_text=_('Associated event'))

    class Meta:
        verbose_name = _('AK Requirement')
        verbose_name_plural = _('AK Requirements')
        ordering = ['name']
        unique_together = ['event', 'name']

    def __str__(self):
        return self.name


class AKType(models.Model):
    """ An AKType allows to associate one or multiple types with an AK, e.g., to better describe the format of that AK
    or to which group of people it is addressed. Types are specified per event and are an optional feature.
    """
    name = models.CharField(max_length=128, verbose_name=_('Name'), help_text=_('Name describing the type'))
    slug = models.SlugField(max_length=30, blank=False, verbose_name=_('Slug'),)
    event = models.ForeignKey(to=Event, on_delete=models.CASCADE, verbose_name=_('Event'),
                              help_text=_('Associated event'))

    class Meta:
        verbose_name = _('AK Type')
        verbose_name_plural = _('AK Types')
        ordering = ['name']
        unique_together = [['event', 'name'], ['event', 'slug']]

    def __str__(self):
        return self.name


class AK(models.Model):
    """ An AK is a slot-based activity to be scheduled during an event.
    """
    name = models.CharField(max_length=256, verbose_name=_('Name'), help_text=_('Name of the AK'),
                            validators=[no_quotation_marks_validator, slugable_validator])
    short_name = models.CharField(max_length=64, blank=True, verbose_name=_('Short Name'),
                                  validators=[no_quotation_marks_validator],
                                  help_text=_('Name displayed in the schedule'))
    description = models.TextField(blank=True, verbose_name=_('Description'), help_text=_('Description of the AK'))

    owners = models.ManyToManyField(to=AKOwner, blank=True, verbose_name=_('Owners'),
                                    help_text=_('Those organizing the AK'))

    # Will be automatically generated in save method if not set
    link = models.URLField(blank=True, verbose_name=_('Web Link'), help_text=_('Link to wiki page'))
    protocol_link = models.URLField(blank=True, verbose_name=_('Protocol Link'), help_text=_('Link to protocol'))

    category = models.ForeignKey(to=AKCategory, on_delete=models.PROTECT, verbose_name=_('Category'),
                                 help_text=_('Category of the AK'))
    types = models.ManyToManyField(to=AKType, blank=True, verbose_name=_('Types'),
                                   help_text=_("This AK is"))
    track = models.ForeignKey(to=AKTrack, blank=True, on_delete=models.SET_NULL, null=True, verbose_name=_('Track'),
                              help_text=_('Track the AK belongs to'))

    reso = models.BooleanField(verbose_name=_('Resolution Intention'), default=False,
                               help_text=_('Intends to submit a resolution'))
    present = models.BooleanField(verbose_name=_("Present this AK"), null=True,
                                  help_text=_("Present results of this AK"))

    requirements = models.ManyToManyField(to=AKRequirement, blank=True, verbose_name=_('Requirements'),
                                          help_text=_("AK's Requirements"))

    conflicts = models.ManyToManyField(to='AK', blank=True, related_name='conflict', verbose_name=_('Conflicting AKs'),
                                       help_text=_('AKs that conflict and thus must not take place at the same time'))
    prerequisites = models.ManyToManyField(to='AK', blank=True, verbose_name=_('Prerequisite AKs'),
                                           help_text=_('AKs that should precede this AK in the schedule'))

    notes = models.TextField(blank=True, verbose_name=_('Organizational Notes'), help_text=_(
            'Notes to organizers. These are public. For private notes, please use the button for private messages '
            'on the detail page of this AK (after creation/editing).'))

    interest = models.IntegerField(default=-1, verbose_name=_('Interest'), help_text=_('Expected number of people'))
    interest_counter = models.IntegerField(default=0, verbose_name=_('Interest Counter'),
                                           help_text=_('People who have indicated interest online'))

    event = models.ForeignKey(to=Event, on_delete=models.CASCADE, verbose_name=_('Event'),
                              help_text=_('Associated event'))

    include_in_export = models.BooleanField(default=True, verbose_name=_('Export?'),
                                            help_text=_("Include AK in wiki export?"))

    history = HistoricalRecords(excluded_fields=['interest', 'interest_counter', 'include_in_export'])

    class Meta:
        verbose_name = _('AK')
        verbose_name_plural = _('AKs')
        unique_together = [['event', 'name'], ['event', 'short_name']]
        ordering = ['pk']

    def __str__(self):
        if self.short_name:
            return self.short_name
        return self.name

    @property
    def details(self):
        """
        Generate a detailed string representation, e.g., for usage in scheduling
        :return: string representation of that AK with all details
        :rtype: str
        """
        # local import to prevent cyclic import
        # pylint: disable=import-outside-toplevel
        from AKModel.availability.models import Availability
        availabilities = ', \n'.join(f'{a.simplified}' for a in Availability.objects.select_related('event')
                                     .filter(ak=self))
        detail_string = f"""{self.name}{" (R)" if self.reso else ""}:

        {self.owners_list}

        {_('Interest')}: {self.interest}"""
        if self.requirements.count() > 0:
            detail_string += f"\n{_('Requirements')}: {', '.join(str(r) for r in self.requirements.all())}"
        if self.types.count() > 0:
            detail_string += f"\n{_('Types')}: {', '.join(str(r) for r in self.types.all())}"

        # Find conflicts
        # (both directions, those specified for this AK and those were this AK was specified as conflict)
        # Deduplicate and order list alphabetically
        conflicts = set()
        if self.conflicts.count() > 0:
            for c in self.conflicts.all():
                conflicts.add(str(c))
        if self.conflict.count() > 0:
            for c in self.conflict.all():
                conflicts.add(str(c))
        if len(conflicts) > 0:
            conflicts = list(conflicts)
            conflicts.sort()
            detail_string += f"\n{_('Conflicts')}: {', '.join(conflicts)}"

        if self.prerequisites.count() > 0:
            detail_string += f"\n{_('Prerequisites')}: {', '.join(str(p) for p in self.prerequisites.all())}"
        detail_string += f"\n{_('Availabilities')}: \n{availabilities}"
        return detail_string

    @property
    def owners_list(self):
        """
        Get a stringified list of stringified representations of all owners

        :return: stringified list of owners
        :rtype: str
        """
        return ", ".join(str(owner) for owner in self.owners.all())

    @property
    def durations_list(self):
        """
        Get a stringified list of stringified representations of all durations of associated slots

        :return: stringified list of durations
        :rtype: str
        """
        return ", ".join(str(slot.duration_simplified) for slot in self.akslot_set.select_related('event').all())

    @property
    def types_list(self):
        """
        Get a stringified list of all types of this AK

        :return: stringified list of types
        :rtype: str
        """
        return ", ".join(str(t) for t in self.types.all())

    @property
    def wish(self):
        """
        Is the AK a wish?
        :return: true if wish, false if not
        :rtype: bool
        """
        return self.owners.count() == 0

    def increment_interest(self):
        """
        Increment the interest counter for this AK by one
        without tracking that change to prevent an unreadable and large history
        """
        self.interest_counter += 1
        self.skip_history_when_saving = True  # pylint: disable=attribute-defined-outside-init
        self.save()
        del self.skip_history_when_saving

    @property
    def availabilities(self):
        """
        Get all availabilities associated to this AK
        :return: availabilities
        :rtype: QuerySet[Availability]
        """
        return "Availability".objects.filter(ak=self)

    @property
    def edit_url(self):
        """
        Get edit URL for this AK
        Will link to frontend if AKSubmission is active, otherwise to the edit view for this object in admin interface

        :return: URL
        :rtype: str
        """
        if apps.is_installed("AKSubmission"):
            return reverse_lazy('submit:ak_edit', kwargs={'event_slug': self.event.slug, 'pk': self.id})
        return reverse_lazy('admin:AKModel_ak_change', kwargs={'object_id': self.id})

    @property
    def detail_url(self):
        """
        Get detail URL for this AK
        Will link to frontend if AKSubmission is active, otherwise to the edit view for this object in admin interface

        :return: URL
        :rtype: str
        """
        if apps.is_installed("AKSubmission"):
            return reverse_lazy('submit:ak_detail', kwargs={'event_slug': self.event.slug, 'pk': self.id})
        return self.edit_url

    def save(self, *args, force_insert=False, force_update=False, using=None, update_fields=None):
        # Auto-Generate Link if not set yet
        if self.link == "":
            link = self.event.base_url + self.name.replace(" ", "_")
            # Truncate links longer than 200 characters (default length of URL fields in django)
            self.link = link[:200]
            # Tell Django that we have updated the link field
            if update_fields is not None:
                update_fields = {"link"}.union(update_fields)
        super().save(*args,
                     force_insert=force_insert, force_update=force_update, using=using, update_fields=update_fields)


class Room(models.Model):
    """ A room describes where an AK can be held.
    """
    name = models.CharField(max_length=64, verbose_name=_('Name'), help_text=_('Name or number of the room'))
    location = models.CharField(max_length=256, blank=True, verbose_name=_('Location'),
                                help_text=_('Name or number of the location'))
    capacity = models.IntegerField(verbose_name=_('Capacity'),
                                   help_text=_('Maximum number of people (-1 for unlimited).'))
    properties = models.ManyToManyField(to=AKRequirement, blank=True, verbose_name=_('Properties'),
                                        help_text=_('AK requirements fulfilled by the room'))

    event = models.ForeignKey(to=Event, on_delete=models.CASCADE, verbose_name=_('Event'),
                              help_text=_('Associated event'))

    class Meta:
        verbose_name = _('Room')
        verbose_name_plural = _('Rooms')
        ordering = ['location', 'name']
        unique_together = ['event', 'name', 'location']

    @property
    def title(self):
        """
        Get title of a room, which consists of location and name if location is set, otherwise only the name

        :return: title
        :rtype: str
        """
        if self.location:
            return f"{self.location} {self.name}"
        return self.name

    def __str__(self):
        return self.title

    def get_time_constraints(self) -> list[str]:
        """Construct list of required time constraint labels."""
        # local import to prevent cyclic import
        # pylint: disable=import-outside-toplevel
        from AKModel.availability.models import Availability

        # check if room is available for the whole event
        # -> no time constraint needs to be introduced
        if Availability.is_event_covered(self.event, self.availabilities.all()):
            time_constraints = []
        else:
            time_constraints = [f"availability-room-{self.pk}"]

        return time_constraints

    def get_fulfilled_room_constraints(self) -> list[str]:
        """Construct list of fulfilled room constraint labels."""
        fulfilled_room_constraints = list(self.properties.values_list("name", flat=True))
        fulfilled_room_constraints.append(f"fixed-room-{self.pk}")

        if not any(constr.startswith("proxy") for constr in fulfilled_room_constraints):
            fulfilled_room_constraints.append("no-proxy")

        fulfilled_room_constraints.sort()
        return fulfilled_room_constraints


class AKSlot(models.Model):
    """ An AK Mapping matches an AK to a room during a certain time.
    """
    ak = models.ForeignKey(to=AK, on_delete=models.CASCADE, verbose_name=_('AK'), help_text=_('AK being mapped'))
    room = models.ForeignKey(to=Room, blank=True, null=True, on_delete=models.SET_NULL, verbose_name=_('Room'),
                             help_text=_('Room the AK will take place in'))
    start = models.DateTimeField(verbose_name=_('Slot Begin'), help_text=_('Time and date the slot begins'),
                                 blank=True, null=True)
    duration = models.DecimalField(max_digits=4, decimal_places=2, default=2, verbose_name=_('Duration'),
                                   help_text=_('Length in hours'))

    fixed = models.BooleanField(default=False, verbose_name=_('Scheduling fixed'),
                                help_text=_('Length and time of this AK should not be changed'))

    event = models.ForeignKey(to=Event, on_delete=models.CASCADE, verbose_name=_('Event'),
                              help_text=_('Associated event'))

    updated = models.DateTimeField(auto_now=True, verbose_name=_("Last update"))

    class Meta:
        verbose_name = _('AK Slot')
        verbose_name_plural = _('AK Slots')
        ordering = ['start', 'room']

    def __str__(self):
        if self.room:
            return f"{self.ak} @ {self.start_simplified} in {self.room}"
        return f"{self.ak} @ {self.start_simplified}"

    @property
    def duration_simplified(self):
        """
        Display duration of slot in format hours:minutes, e.g. 1.5 -> "1:30"
        """
        hours, minutes = divmod(self.duration * 60, 60)
        return f"{int(hours)}:{int(minutes):02}"

    @property
    def start_simplified(self):
        """
        Display start time of slot in format weekday + time, e.g. "Fri 14:00"
        """
        if self.start is None:
            return _("Not scheduled yet")
        return self.start.astimezone(self.event.timezone).strftime('%a %H:%M')

    @property
    def time_simplified(self):
        """
        Display start and end time of slot in format weekday + time, e.g. "Fri 14:00 - 15:30" or "Fri 22:00 - Sat 02:00"
        """
        if self.start is None:
            return _("Not scheduled yet")

        start = self.start.astimezone(self.event.timezone)
        end = self.end.astimezone(self.event.timezone)

        return (f"{start.strftime('%a %H:%M')} - "
                f"{end.strftime('%H:%M') if start.day == end.day else end.strftime('%a %H:%M')}")

    @property
    def end(self):
        """
        Retrieve end time of the AK slot
        """
        return self.start + timedelta(hours=float(self.duration))

    @property
    def seconds_since_last_update(self):
        """
        Return minutes since last update
        :return: minutes since last update
        :rtype: float
        """
        return (timezone.now() - self.updated).total_seconds()

    def overlaps(self, other: "AKSlot"):
        """
        Check whether two slots overlap

        :param other: second slot to compare with
        :return: true if they overlap, false if not:
        :rtype: bool
        """
        return self.start < other.end <= self.end or self.start <= other.start < self.end

    def save(self, *args, force_insert=False, force_update=False, using=None, update_fields=None):
        # Make sure duration is not longer than the event
        if update_fields is None or 'duration' in update_fields:
            event_duration = self.event.end - self.event.start
            event_duration_hours = event_duration.days * 24 + event_duration.seconds // 3600
            self.duration = min(self.duration, event_duration_hours)
        super().save(*args,
                     force_insert=force_insert, force_update=force_update, using=using, update_fields=update_fields)

    def get_room_constraints(self, export_scheduled_aks_as_fixed: bool = False) -> list[str]:
        """Construct list of required room constraint labels."""
        room_constraints = list(self.ak.requirements.values_list("name", flat=True).order_by())
        if (export_scheduled_aks_as_fixed or self.fixed) and self.room is not None:
            room_constraints.append(f"fixed-room-{self.room.pk}")

        if not any(constr.startswith("proxy") for constr in room_constraints):
            room_constraints.append("no-proxy")

        room_constraints.sort()
        return room_constraints

    def get_time_constraints(self, export_scheduled_aks_as_fixed: bool = False) -> list[str]:
        """Construct list of required time constraint labels."""
        # local import to prevent cyclic import
        # pylint: disable=import-outside-toplevel
        from AKModel.availability.models import Availability

        def _owner_time_constraints(owner: AKOwner):
            owner_avails = owner.availabilities.all()
            if not owner_avails or Availability.is_event_covered(self.event, owner_avails):
                return []
            return [f"availability-person-{owner.pk}"]

        # check if ak resp. owner is available for the whole event
        # -> no time constraint needs to be introduced
        if (export_scheduled_aks_as_fixed or self.fixed) and self.start is not None:
            time_constraints = [f"fixed-akslot-{self.id}"]
        elif not Availability.is_event_covered(self.event, self.ak.availabilities.all()):
            time_constraints = [f"availability-ak-{self.ak.pk}"]
        else:
            time_constraints = []

        if self.ak.reso:
            time_constraints.append("resolution")
        for owner in self.ak.owners.all():
            time_constraints.extend(_owner_time_constraints(owner))

        if self.ak.category:
            category_constraints = AKCategory.create_category_optimizer_constraints([self.ak.category])
            time_constraints.extend(category_constraints)

        time_constraints.sort()
        return time_constraints

    @property
    def export_duration(self) -> int:
        """Number of discrete export timeslots covered by this AKSlot."""
        export_duration = self.duration / self.event.export_slot
        # We need to return an int, so we round up.
        # If the exact result for `export_duration` is an integer `k`,
        # FLOP inaccuracies could yield `k + eps`. Then, rounding up
        # would return `k + 1` instead of `k`. To avoid this, we subtract
        # a small epsilon before rounding.
        return math.ceil(export_duration - settings.EXPORT_CEIL_OFFSET_EPS)

    @property
    def type_names(self):
        """Ordered queryset of the names of all types of this slot's AK."""
        return self.ak.types.values_list("name", flat=True).order_by()

    @property
    def conflict_pks(self) -> list[int]:
        """Ordered queryset of the PKs of all AKSlots that in conflict to this slot."""
        conflict_slots = AKSlot.objects.filter(ak__in=self.ak.conflicts.all())
        other_ak_slots = AKSlot.objects.filter(ak=self.ak).exclude(pk=self.pk)
        return list((conflict_slots | other_ak_slots).values_list("pk", flat=True).order_by())

    @property
    def depencency_pks(self) -> list[int]:
        """Ordered queryset of the PKs of all AKSlots that this slot depends on."""
        dependency_slots = AKSlot.objects.filter(ak__in=self.ak.prerequisites.all())
        return list(dependency_slots.values_list("pk", flat=True).order_by())


class AKOrgaMessage(models.Model):
    """
    Model representing confidential messages to the organizers/scheduling people, belonging to a certain AK
    """
    ak = models.ForeignKey(to=AK, on_delete=models.CASCADE, verbose_name=_('AK'),
                           help_text=_('AK this message belongs to'))
    text = models.TextField(verbose_name=_("Message text"),
                            help_text=_("Message to the organizers. This is not publicly visible."))
    timestamp = models.DateTimeField(auto_now_add=True)
    event = models.ForeignKey(to=Event, on_delete=models.CASCADE, verbose_name=_('Event'),
                              help_text=_('Associated event'))
    resolved = models.BooleanField(verbose_name=_('Resolved'), default=False,
                                   help_text=_('This message has been resolved (no further action needed)'))

    class Meta:
        verbose_name = _('AK Orga Message')
        verbose_name_plural = _('AK Orga Messages')
        ordering = ['-timestamp']

    def __str__(self):
        return f'AK Orga Message for "{self.ak}" @ {self.timestamp}'


class ConstraintViolation(models.Model):
    """
    Model to represent any kind of constraint violation

    Can have two different severities: violation and warning
    The list of possible types is defined in :class:`ViolationType`
    Depending on the type, different fields (references to other models) will be filled. Each violation should always
    be related to an event and at least on other instance of a causing entity
    """

    class Meta:
        verbose_name = _('Constraint Violation')
        verbose_name_plural = _('Constraint Violations')
        ordering = ['-timestamp']

    class ViolationType(models.TextChoices):
        """
        Possible types of violations with their text representation
        """
        OWNER_TWO_SLOTS = 'ots', _('Owner has two parallel slots')
        SLOT_OUTSIDE_AVAIL = 'soa', _('AK Slot was scheduled outside the AK\'s availabilities')
        ROOM_TWO_SLOTS = 'rts', _('Room has two AK slots scheduled at the same time')
        REQUIRE_NOT_GIVEN = 'rng', _('Room does not satisfy the requirement of the scheduled AK')
        AK_CONFLICT_COLLISION = 'acc', _('AK Slot is scheduled at the same time as an AK listed as a conflict')
        AK_BEFORE_PREREQUISITE = 'abp', _('AK Slot is scheduled before an AK listed as a prerequisite')
        AK_AFTER_RESODEADLINE = 'aar', _(
                'AK Slot for AK with intention to submit a resolution is scheduled after resolution deadline')
        AK_CATEGORY_MISMATCH = 'acm', _('AK Slot in a category is outside that categories availabilities')
        AK_SLOT_COLLISION = 'asc', _('Two AK Slots for the same AK scheduled at the same time')
        ROOM_CAPACITY_EXCEEDED = 'rce', _('Room does not have enough space for interest in scheduled AK Slot')
        SLOT_OUTSIDE_EVENT = 'soe', _('AK Slot is scheduled outside the event\'s availabilities')

    class ViolationLevel(models.IntegerChoices):
        """
        Possible severities/levels of a CV
        """
        WARNING = 1, _('Warning')
        VIOLATION = 10, _('Violation')

    type = models.CharField(verbose_name=_('Type'), max_length=3, choices=ViolationType.choices,
                            help_text=_('Type of violation, i.e. what kind of constraint was violated'))
    level = models.PositiveSmallIntegerField(verbose_name=_('Level'), choices=ViolationLevel.choices,
                                             help_text=_('Severity level of the violation'))

    event = models.ForeignKey(to=Event, on_delete=models.CASCADE, verbose_name=_('Event'),
                              help_text=_('Associated event'))

    # Possible "causes":
    aks = models.ManyToManyField(to=AK, blank=True, verbose_name=_('AKs'),
                                 help_text=_('AK(s) belonging to this constraint'))
    ak_slots = models.ManyToManyField(to=AKSlot, blank=True, verbose_name=_('AK Slots'),
                                      help_text=_('AK Slot(s) belonging to this constraint'))
    ak_owner = models.ForeignKey(to=AKOwner, on_delete=models.CASCADE, blank=True, null=True,
                                 verbose_name=_('AK Owner'), help_text=_('AK Owner belonging to this constraint'))
    room = models.ForeignKey(to=Room, on_delete=models.CASCADE, blank=True, null=True, verbose_name=_('Room'),
                             help_text=_('Room belonging to this constraint'))
    requirement = models.ForeignKey(to=AKRequirement, on_delete=models.CASCADE, blank=True, null=True,
                                    verbose_name=_('AK Requirement'),
                                    help_text=_('AK Requirement belonging to this constraint'))
    category = models.ForeignKey(to=AKCategory, on_delete=models.CASCADE, blank=True, null=True,
                                 verbose_name=_('AK Category'), help_text=_('AK Category belonging to this constraint'))

    comment = models.TextField(verbose_name=_('Comment'), help_text=_('Comment or further details for this violation'),
                               blank=True)

    timestamp = models.DateTimeField(auto_now_add=True, verbose_name=_('Timestamp'), help_text=_('Time of creation'))
    manually_resolved = models.BooleanField(verbose_name=_('Manually Resolved'), default=False,
                                            help_text=_('Mark this violation manually as resolved'))

    fields = ['ak_owner', 'room', 'requirement', 'category', 'comment']
    fields_mm = ['_aks', '_ak_slots']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aks_tmp = set()
        self.ak_slots_tmp = set()

    def get_details(self):
        """
        Get details of this constraint (all fields connected to it)
        :return: string of details
        :rtype: str
        """
        # Stringify aks and ak slots fields (m2m)
        output = [f"{_('AKs')}: {self._aks_str}",
                  f"{_('AK Slots')}: {self._ak_slots_str}"]

        # Stringify all other fields
        for field in self.fields:
            a = getattr(self, field, None)
            if a is not None and str(a) != '':
                output.append(f"{field}: {a}")
        return ", ".join(output)

    get_details.short_description = _('Details')

    @property
    def details(self):
        """
        Property: Details
        """
        return self.get_details()

    @property
    def edit_url(self) -> str:
        """
        Property: Edit URL for this CV
        """
        return reverse_lazy('admin:AKModel_constraintviolation_change', kwargs={'object_id': self.pk})

    @property
    def level_display(self) -> str:
        """
        Property: Severity as string
        """
        return self.get_level_display()

    @property
    def type_display(self) -> str:
        """
        Property: Type as string
        """
        return self.get_type_display()

    @property
    def timestamp_display(self) -> str:
        """
        Property: Creation timestamp as string
        """
        return self.timestamp.astimezone(self.event.timezone).strftime('%d.%m.%y %H:%M')

    @property
    def _aks(self):
        """
        Get all AKs belonging to this constraint violation

        The distinction between real and tmp relationships is needed since many to many
        relations only work for objects already persisted in the database

        :return: set of all AKs belonging to this constraint violation
        :rtype: set(AK)
        """
        if self.pk and self.pk > 0:
            return set(self.aks.all())
        return self.aks_tmp

    @property
    def _aks_str(self) -> str:
        """
        Property: AKs as string
        """
        if self.pk and self.pk > 0:
            return ', '.join(str(a) for a in self.aks.all())
        return ', '.join(str(a) for a in self.aks_tmp)

    @property
    def _ak_slots(self):
        """
        Get all AK Slots belonging to this constraint violation

        The distinction between real and tmp relationships is needed since many to many
        relations only work for objects already persisted in the database

        :return: set of all AK Slots belonging to this constraint violation
        :rtype: set(AKSlot)
        """
        if self.pk and self.pk > 0:
            return set(self.ak_slots.all())
        return self.ak_slots_tmp

    @property
    def _ak_slots_str(self) -> str:
        """
        Property: Slots as string
        """
        if self.pk and self.pk > 0:
            return ', '.join(str(a) for a in self.ak_slots.select_related('event').all())
        return ', '.join(str(a) for a in self.ak_slots_tmp)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Store temporary m2m-relations in db
        for ak in self.aks_tmp:
            self.aks.add(ak)
        for ak_slot in self.ak_slots_tmp:
            self.ak_slots.add(ak_slot)

    def __str__(self):
        return f"{self.get_level_display()}: {self.get_type_display()} [{self.get_details()}]"

    def matches(self, other):
        """
        Check whether one constraint violation instance matches another,
        this means has the same type, room, requirement, owner, category
        as well as the same lists of aks and ak slots.
        PK, timestamp, comments and manual resolving are ignored.

        :param other: second instance to compare to
        :type other: ConstraintViolation
        :return: true if both instances are similar in the way described, false if not
        :rtype: bool
        """
        if not isinstance(other, ConstraintViolation):
            return False
        # Check type
        if self.type != other.type:
            return False
        # Make sure both have the same aks and ak slots
        for field_mm in self.fields_mm:
            s: set = getattr(self, field_mm)
            o: set = getattr(other, field_mm)
            if len(s) != len(o):
                return False
            if len(s.intersection(o)) != len(s):
                return False
        # Check other "defining" fields
        for field in self.fields:
            if getattr(self, field) != getattr(other, field):
                return False
        return True


class DefaultSlot(models.Model):
    """
    Model representing a default slot,
    i.e., a prefered slot to use for typical AKs in the schedule to guarantee enough breaks etc.
    """

    class Meta:
        verbose_name = _('Default Slot')
        verbose_name_plural = _('Default Slots')
        ordering = ['-start']

    start = models.DateTimeField(verbose_name=_('Slot Begin'), help_text=_('Time and date the slot begins'))
    end = models.DateTimeField(verbose_name=_('Slot End'), help_text=_('Time and date the slot ends'))

    event = models.ForeignKey(to=Event, on_delete=models.CASCADE, verbose_name=_('Event'),
                              help_text=_('Associated event'))

    primary_categories = models.ManyToManyField(to=AKCategory, verbose_name=_('Primary categories'), blank=True,
                                                help_text=_(
                                                        'Categories that should be assigned to this slot primarily'))

    @property
    def start_simplified(self) -> str:
        """
        Property: Simplified version of the start timetstamp (weekday, hour, minute) as string
        """
        return self.start.astimezone(self.event.timezone).strftime('%a %H:%M')

    @property
    def start_iso(self) -> str:
        """
        Property: Start timestamp as ISO timestamp for usage in calendar views
        """
        return timezone.localtime(self.start, self.event.timezone).strftime("%Y-%m-%dT%H:%M:%S")

    @property
    def end_simplified(self) -> str:
        """
        Property: Simplified version of the end timetstamp (weekday, hour, minute) as string
        """
        return self.end.astimezone(self.event.timezone).strftime('%a %H:%M')

    @property
    def end_iso(self) -> str:
        """
        Property: End timestamp as ISO timestamp for usage in calendar views
        """
        return timezone.localtime(self.end, self.event.timezone).strftime("%Y-%m-%dT%H:%M:%S")

    def __str__(self):
        return f"{self.event}: {self.start_simplified} - {self.end_simplified}"
