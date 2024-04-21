import itertools
from datetime import timedelta

from django.db import models
from django.apps import apps
from django.db.models import Count
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.datetime_safe import datetime
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords
from timezone_field import TimeZoneField


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
              _('Opening time for expression of interest. When left blank, no interest indication will be possible.'))

    interest_end = models.DateTimeField(verbose_name=_('Interest Window End'), blank=True, null=True,
                                        help_text=_('Closing time for expression of interest.'))

    public = models.BooleanField(verbose_name=_('Public event'), default=True,
                                 help_text=_('Show this event on overview page.'))

    active = models.BooleanField(verbose_name=_('Active State'), help_text=_('Marks currently active events'))
    plan_hidden = models.BooleanField(verbose_name=_('Plan Hidden'), help_text=_('Hides plan for non-staff users'),
                                      default=True)
    plan_published_at = models.DateTimeField(verbose_name=_('Plan published at'), blank=True, null=True,
                                         help_text=_('Timestamp at which the plan was published'))

    base_url = models.URLField(verbose_name=_("Base URL"), help_text=_("Prefix for wiki link construction"), blank=True)
    wiki_export_template_name = models.CharField(verbose_name=_("Wiki Export Template Name"), blank=True, max_length=50)
    default_slot = models.DecimalField(max_digits=4, decimal_places=2, default=2, verbose_name=_('Default Slot Length'),
                                       help_text=_('Default length in hours that is assumed for AKs in this event.'))

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
            event = Event.objects.order_by('start').filter(start__gt=datetime.now()).first()
        return event

    def get_categories_with_aks(self, wishes_seperately=False,
                                filter_func=lambda ak: True, hide_empty_categories=False):
        """
        Get AKCategories as well as a list of AKs belonging to the category for this event

        :param wishes_seperately: Return wishes as individual list.
        :type wishes_seperately: bool
        :param filter_func: Optional filter predicate, only include AK in list if filter returns True
        :type filter_func: (AK)->bool
        :return: list of category-AK-list-tuples, optionally the additional list of AK wishes
        :rtype: list[(AKCategory, list[AK])] [, list[AK]]
        """
        categories = self.akcategory_set.select_related('event').all()
        categories_with_aks = []
        ak_wishes = []

        # Fill lists by iterating
        # A different behavior is needed depending on whether wishes should show up inside their categories
        # or as a separate category

        def _get_category_aks(category):
            """
            Get all AKs belonging to a category
            Use joining and prefetching to reduce the number of necessary SQL queries

            :param category: category the AKs should belong to
            :return: QuerySet over AKs
            :return: QuerySet[AK]
            """
            return category.ak_set.select_related('event').prefetch_related('owners', 'akslot_set').all()

        if wishes_seperately:
            for category in categories:
                ak_list = []
                for ak in _get_category_aks(category):
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
            for ak in _get_category_aks(category):
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


class AKOwner(models.Model):
    """ An AKOwner describes the person organizing/holding an AK.
    """
    name = models.CharField(max_length=64, verbose_name=_('Nickname'), help_text=_('Name to identify an AK owner by'))
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
                                             help_text=_("Present AKs of this category by default "
                                                 "if AK owner did not specify whether this AK should be presented?"))

    event = models.ForeignKey(to=Event, on_delete=models.CASCADE, verbose_name=_('Event'),
                              help_text=_('Associated event'))

    class Meta:
        verbose_name = _('AK Category')
        verbose_name_plural = _('AK Categories')
        ordering = ['name']
        unique_together = ['event', 'name']

    def __str__(self):
        return self.name


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

    event = models.ForeignKey(to=Event, on_delete=models.CASCADE, verbose_name=_('Event'),
                              help_text=_('Associated event'))

    class Meta:
        verbose_name = _('AK Requirement')
        verbose_name_plural = _('AK Requirements')
        ordering = ['name']
        unique_together = ['event', 'name']

    def __str__(self):
        return self.name


class AK(models.Model):
    """ An AK is a slot-based activity to be scheduled during an event.
    """
    name = models.CharField(max_length=256, verbose_name=_('Name'), help_text=_('Name of the AK'))
    short_name = models.CharField(max_length=64, blank=True, verbose_name=_('Short Name'),
                                  help_text=_('Name displayed in the schedule'))
    description = models.TextField(blank=True, verbose_name=_('Description'), help_text=_('Description of the AK'))

    owners = models.ManyToManyField(to=AKOwner, blank=True, verbose_name=_('Owners'),
                                    help_text=_('Those organizing the AK'))

    # Will be automatically generated in save method if not set
    link = models.URLField(blank=True, verbose_name=_('Web Link'), help_text=_('Link to wiki page'))
    protocol_link = models.URLField(blank=True, verbose_name=_('Protocol Link'), help_text=_('Link to protocol'))

    category = models.ForeignKey(to=AKCategory, on_delete=models.PROTECT, verbose_name=_('Category'),
                                 help_text=_('Category of the AK'))
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

    history = HistoricalRecords(excluded_fields=['interest_counter', 'include_in_export'])

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
        if self.conflicts.count() > 0:
            detail_string += f"\n{_('Conflicts')}: {', '.join(str(c) for c in self.conflicts.all())}"
        if self.prerequisites.count() > 0:
            detail_string += f"\n{_('Prerequisites')}: {', '.join(str(p) for p in self.prerequisites.all())}"
        detail_string += f"\n{_('Availabilities')}: \n{availabilities}"
        return detail_string

    @property
    def owners_list(self):
        """
        Get a list of stringified representations of all owners

        :return: list of owners
        :rtype: List[str]
        """
        return ", ".join(str(owner) for owner in self.owners.all())

    @property
    def durations_list(self):
        """
        Get a list of stringified representations of all durations of associated slots

        :return: list of durations
        :rtype: List[str]
        """
        return ", ".join(str(slot.duration_simplified) for slot in self.akslot_set.select_related('event').all())

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

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        # Auto-Generate Link if not set yet
        if self.link == "":
            link = self.event.base_url + self.name.replace(" ", "_")
            # Truncate links longer than 200 characters (default length of URL fields in django)
            self.link = link[:200]
            # Tell Django that we have updated the link field
            if update_fields is not None:
                update_fields = {"link"}.union(update_fields)
        super().save(force_insert, force_update, using, update_fields)


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
        Check wether two slots overlap

        :param other: second slot to compare with
        :return: true if they overlap, false if not:
        :rtype: bool
        """
        return self.start < other.end <= self.end or self.start <= other.start < self.end


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
                                            help_text=_('Categories that should be assigned to this slot primarily'))

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
