from datetime import timedelta

from django.utils.datetime_safe import datetime
import itertools

from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords
from timezone_field import TimeZoneField


class Event(models.Model):
    """ An event supplies the frame for all Aks.
    """
    name = models.CharField(max_length=64, unique=True, verbose_name=_('Name'),
                            help_text=_('Name or iteration of the event'))
    slug = models.SlugField(max_length=32, unique=True, verbose_name=_('Short Form'),
                            help_text=_('Short name of letters/numbers/dots/dashes/underscores used in URLs.'))

    place = models.CharField(max_length=128, blank=True, verbose_name=_('Place'),
                             help_text=_('City etc. the event takes place in'))
    timezone = TimeZoneField(default='Europe/Berlin', display_GMT_offset=True, blank=False,
                             verbose_name=_('Time Zone'), help_text=_('Time Zone where this event takes place in'))
    start = models.DateTimeField(verbose_name=_('Start'), help_text=_('Time the event begins'))
    end = models.DateTimeField(verbose_name=_('End'), help_text=_('Time the event ends'))

    active = models.BooleanField(verbose_name=_('Active State'), help_text=_('Marks currently active events'))

    base_url = models.URLField(verbose_name=_("Base URL"), help_text=_("Prefix for wiki link construction"), blank=True)
    default_slot = models.DecimalField(max_digits=4, decimal_places=2, default=2, verbose_name=_('Default Slot Length'),
                                       help_text=_('Default length in hours that is assumed for AKs in this event.'))

    contact_email = models.EmailField(verbose_name=_("Contact email address"), blank=True,
                                      help_text=_(
                                          "An email address that is displayed on every page and can be used for all kinds of questions"))

    class Meta:
        verbose_name = _('Event')
        verbose_name_plural = _('Events')
        ordering = ['-start']

    def __str__(self):
        return self.name

    @staticmethod
    def get_by_slug(slug):
        return Event.objects.get(slug=slug)

    @staticmethod
    def get_next_active():
        # Get first active event taking place
        event = Event.objects.filter(active=True).order_by('start').first()
        # No active event? Return the next event taking place
        if event is None:
            event = Event.objects.order_by('start').filter(start__gt=datetime.now()).first()
        return event


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
        max_length = self._meta.get_field('slug').max_length

        slug_candidate = slugify(self.name)[:max_length]
        if not AKOwner.objects.filter(event=self.event, slug=slug_candidate).exists():
            self.slug = slug_candidate
            return
        slug_candidate = slugify(slug_candidate + '_' + self.institution)[:max_length]
        if not AKOwner.objects.filter(event=self.event, slug=slug_candidate).exists():
            self.slug = slug_candidate
            return
        for i in itertools.count(1):
            if not AKOwner.objects.filter(event=self.event, slug=slug_candidate).exists():
                break
            digits = len(str(i))
            slug_candidate = '{}-{}'.format(slug_candidate[:-(digits + 1)], i)

        self.slug = slug_candidate

    def save(self, *args, **kwargs):
        if not self.slug:
            self._generate_slug()

        super().save(*args, **kwargs)

    @staticmethod
    def get_by_slug(event, slug):
        return AKOwner.objects.get(event=event, slug=slug)


class AKCategory(models.Model):
    """ An AKCategory describes the characteristics of an AK, e.g. content vs. recreational.
    """
    name = models.CharField(max_length=64, verbose_name=_('Name'), help_text=_('Name of the AK Category'))
    color = models.CharField(max_length=7, blank=True, verbose_name=_('Color'), help_text=_('Color for displaying'))
    description = models.TextField(blank=True, verbose_name=_("Description"),
                                   help_text=_("Short description of this AK Category"))

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


class AKTag(models.Model):
    """ An AKTag is a keyword given to an AK by (one of) its owner(s).
    """
    name = models.CharField(max_length=64, unique=True, verbose_name=_('Name'), help_text=_('Name of the AK Tag'))

    class Meta:
        verbose_name = _('AK Tag')
        verbose_name_plural = _('AK Tags')
        ordering = ['name']

    def __str__(self):
        return self.name


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

    # TODO generate automatically
    link = models.URLField(blank=True, verbose_name=_('Web Link'), help_text=_('Link to wiki page'))

    category = models.ForeignKey(to=AKCategory, on_delete=models.PROTECT, verbose_name=_('Category'),
                                 help_text=_('Category of the AK'))
    tags = models.ManyToManyField(to=AKTag, blank=True, verbose_name=_('Tags'), help_text=_('Tags provided by owners'))
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
        'Notes to organizers. These are public. For private notes, please send an e-mail.'))

    interest = models.IntegerField(default=-1, verbose_name=_('Interest'), help_text=_('Expected number of people'))
    interest_counter = models.IntegerField(default=0, verbose_name=_('Interest Counter'),
                                           help_text=_('People who have indicated interest online'))

    event = models.ForeignKey(to=Event, on_delete=models.CASCADE, verbose_name=_('Event'),
                              help_text=_('Associated event'))

    history = HistoricalRecords()

    class Meta:
        verbose_name = _('AK')
        verbose_name_plural = _('AKs')
        unique_together = [['event', 'name'], ['event', 'short_name']]

    def __str__(self):
        if self.short_name:
            return self.short_name
        return self.name

    @property
    def owners_list(self):
        return ", ".join(str(owner) for owner in self.owners.all())

    @property
    def durations_list(self):
        return ", ".join(str(slot.duration) for slot in self.akslot_set.all())

    @property
    def wish(self):
        return self.owners.count() == 0

    def increment_interest(self):
        self.interest_counter += 1
        self.save()


class Room(models.Model):
    """ A room describes where an AK can be held.
    """
    name = models.CharField(max_length=64, verbose_name=_('Name'), help_text=_('Name or number of the room'))
    building = models.CharField(max_length=256, blank=True, verbose_name=_('Building'),
                                help_text=_('Name or number of the building'))
    capacity = models.IntegerField(verbose_name=_('Capacity'), help_text=_('Maximum number of people'))
    properties = models.ManyToManyField(to=AKRequirement, blank=True, verbose_name=_('Properties'),
                                        help_text=_('AK requirements fulfilled by the room'))

    event = models.ForeignKey(to=Event, on_delete=models.CASCADE, verbose_name=_('Event'),
                              help_text=_('Associated event'))

    class Meta:
        verbose_name = _('Room')
        verbose_name_plural = _('Rooms')
        ordering = ['building', 'name']
        unique_together = ['event', 'name', 'building']

    @property
    def title(self):
        if self.building:
            return f"{self.building} {self.name}"
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
    def start_simplified(self):
        """
        Display start time of slot in format weekday + time, e.g. "Fri 14:00"
        """
        if self.start is None:
            return _("Not scheduled yet")
        return self.start.astimezone(self.event.timezone).strftime('%a %H:%M')

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
