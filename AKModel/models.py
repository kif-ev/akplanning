# Create your models here.

from django.db import models


class Event(models.Model):
    """ An event supplies the frame for all Aks.
    """
    name = models.CharField(max_length=64, unique=True, verbose_name='Name', help_text='Name or iteration of the event')
    start = models.DateTimeField(verbose_name='Start', help_text='Time the event begins')
    end = models.DateTimeField(verbose_name='End', help_text='Time the event ends')
    place = models.CharField(max_length=128, verbose_name='Place', help_text='City etc. where the event takes place')
    active = models.BooleanField(verbose_name='Active State', help_text='Marks currently active events')


class AKOwner(models.Model):
    """ An AKOwner describes the person organizing/holding an AK.
    """
    name = models.CharField(max_length=256, verbose_name='Nickname', help_text='Name used to identify an AK owner')
    email = models.EmailField(max_length=128, blank=True, verbose_name='E-Mail Address', help_text='Contact e-mail')
    institution = models.CharField(max_length=128, blank=True, verbose_name='Institution', help_text='University etc.')
    link = models.URLField(blank=True, verbose_name='Web Link', help_text='Link to Homepage')

    event = models.ForeignKey(to=Event, on_delete=models.CASCADE, verbose_name='Event', help_text='Matching event')

    class Meta:
        verbose_name = 'AK Owner'
        verbose_name_plural = 'AK Owners'
        ordering = ['name']
        unique_together = [['name', 'institution']]


class AKType(models.Model):
    """ An AKType describes the characteristics of an AK, e.g. content vs. recreational.
    """
    name = models.CharField(max_length=64, unique=True, verbose_name='Name', help_text='Name of the AK Type')
    color = models.CharField(max_length=7, blank=True, verbose_name='Color', help_text='Color to display this type in')

    # TODO model availability

    class Meta:
        verbose_name = 'AK Type'
        verbose_name_plural = 'AK Types'
        ordering = ['name']


class AKTrack(models.Model):
    """ An AKTrack describes a set of semantically related AKs.
    """
    name = models.CharField(max_length=64, unique=True, verbose_name='Name', help_text='Name of the AK Track')
    color = models.CharField(max_length=7, blank=True, verbose_name='Color', help_text='Color to display this track in')

    class Meta:
        verbose_name = 'AK Track'
        verbose_name_plural = 'AK Tracks'
        ordering = ['name']


class AKTag(models.Model):
    """ An AKTag is a keyword given to an AK by (one of) its owner(s).
    """
    name = models.CharField(max_length=64, unique=True, verbose_name='Name', help_text='Name of the AK Tag')

    class Meta:
        verbose_name = 'AK Tag'
        verbose_name_plural = 'AK Tags'
        ordering = ['name']


class AKRequirement(models.Model):
    """ An AKRequirement describes something needed to hold an AK, e.g. infrastructure.
    """
    name = models.CharField(max_length=128, unique=True, verbose_name='Name', help_text='Name of the AK Requirement')

    event = models.ForeignKey(to=Event, on_delete=models.CASCADE, verbose_name='Event', help_text='Matching event')

    class Meta:
        verbose_name = 'AK Requirement'
        verbose_name_plural = 'AK Requirements'
        ordering = ['name']


class AK(models.Model):
    """ An AK is a slot-based activity to be scheduled during an event.
    """
    name = models.CharField(max_length=256, unique=True, verbose_name='Name', help_text='Name of the AK')
    short_name = models.CharField(max_length=64, unique=True, blank=True, verbose_name='Short Name',
                                  help_text='Name displayed in schedule')
    description = models.TextField(blank=True, verbose_name='Description', help_text='Description of the AK')

    owners = models.ManyToManyField(to=AKOwner, verbose_name='Owners', help_text='Those organizing the AK')

    # TODO generate automatically
    link = models.URLField(blank=True, verbose_name='Web Link', help_text='Link to wiki page')

    type = models.ForeignKey(to=AKType, on_delete=models.PROTECT, verbose_name='Type', help_text='Type of the AK')
    tags = models.ManyToManyField(to=AKTag, blank=True, verbose_name='Tags', help_text='Tags provided by AK owners')
    track = models.ForeignKey(to=AKTrack, on_delete=models.SET_NULL, null=True, verbose_name='Track',
                              help_text='Track the AK belongs to.')

    reso = models.BooleanField(verbose_name='Resolution Intention', default=False, help_text='Intends to submit a reso')
    requirements = models.ManyToManyField(to=AKRequirement, blank=True, verbose_name='Requirements',
                                          help_text="AK's Requirements")

    conflicts = models.ManyToManyField(to='AK', blank=True, related_name='conflict', verbose_name='Conflicting AKs',
                                       help_text='AKs that conflict and thus must not take place at the same time')
    prerequisites = models.ManyToManyField(to='AK', blank=True, verbose_name='Prerequisite AKs',
                                           help_text='AKs that should precede this AK in the schedule')
    # TODO model availability

    notes = models.TextField(blank=True, verbose_name='Internal Notes', help_text='Notes to organizers')

    interest = models.IntegerField(default=-1, verbose_name='Interest', help_text='Expected number of people to attend')

    event = models.ForeignKey(to=Event, on_delete=models.CASCADE, verbose_name='Event', help_text='Matching event')

    class Meta:
        verbose_name = 'AK'
        verbose_name_plural = 'AKs'
