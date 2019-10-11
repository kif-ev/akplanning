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
