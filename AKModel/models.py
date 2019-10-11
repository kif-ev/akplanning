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
