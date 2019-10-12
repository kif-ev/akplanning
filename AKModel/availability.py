# This part of the code was adapted from pretalx (https://github.com/pretalx/pretalx)
# Copyright 2017-2019, Tobias Kunze
# Original Copyrights licensed under the Apache License, Version 2.0 http://www.apache.org/licenses/LICENSE-2.0
# Changes are marked in the code

import datetime
from typing import List

from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from AKModel.models import Event, AKOwner, Room, AK, AKType

zero_time = datetime.time(0, 0)


# CHANGES:
# ScopeManager and LogMixin removed as they are not used in this project
# adapted to event, people and room models
# remove serialization as requirements are not covered
# add translation
# add meta class
# enable availabilites for AKs and AKTypes
# add verbose names and help texts to model attributes
class Availability(models.Model):
    """The Availability class models when people or rooms are available for.

    The power of this class is not within its rather simple data model,
    but with the operations available on it. An availability object can
    span multiple days, but due to our choice of input widget, it will
    usually only span a single day at most.
    """
    event = models.ForeignKey(
        to=Event,
        related_name='availabilities',
        on_delete=models.CASCADE,
        verbose_name=_('Event'),
        help_text=_('Associated event'),
    )
    person = models.ForeignKey(
        to=AKOwner,
        related_name='availabilities',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_('Person'),
        help_text=_('Person whose availability this is'),
    )
    room = models.ForeignKey(
        to=Room,
        related_name='availabilities',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_('Room'),
        help_text=_('Room whose availability this is'),
    )
    ak = models.ForeignKey(
        to=AK,
        related_name='availabilities',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_('AK'),
        help_text=_('AK whose availability this is'),
    )
    ak_type = models.ForeignKey(
        to=AKType,
        related_name='availabilities',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_('AK Type'),
        help_text=_('AK Type whose availability this is'),
    )
    start = models.DateTimeField()
    end = models.DateTimeField()

    def __str__(self) -> str:
        person = self.person.name if self.person else None
        room = getattr(self.room, 'name', None)
        event = getattr(getattr(self, 'event', None), 'name', None)
        ak = getattr(self.ak, 'name', None)
        ak_type = getattr(self.ak_type, 'name', None)
        return f'Availability(event={event}, person={person}, room={room}, ak={ak}, ak type={ak_type})'

    def __hash__(self):
        return hash((getattr(self, 'event', None), self.person, self.room, self.ak, self.ak_type, self.start, self.end))

    def __eq__(self, other: 'Availability') -> bool:
        """Comparisons like ``availability1 == availability2``.

        Checks if ``event``, ``person``, ``room``, ``ak``, ``ak_type``, ``start`` and ``end``
        are the same.
        """
        return all(
            [
                getattr(self, attribute, None) == getattr(other, attribute, None)
                for attribute in ['event', 'person', 'room', 'ak', 'ak_type', 'start', 'end']
            ]
        )

    @cached_property
    def all_day(self) -> bool:
        """Checks if the Availability spans one (or, technically: multiple)
        complete day."""
        return self.start.time() == zero_time and self.end.time() == zero_time

    def overlaps(self, other: 'Availability', strict: bool) -> bool:
        """Test if two Availabilities overlap.

        :param other:
        :param strict: Only count a real overlap as overlap, not direct adjacency.
        """

        if not isinstance(other, Availability):
            raise Exception('Please provide an Availability object')

        if strict:
            return (
                    (self.start <= other.start < self.end)
                    or (self.start < other.end <= self.end)
                    or (other.start <= self.start < other.end)
                    or (other.start < self.end <= other.end)
            )
        return (
                (self.start <= other.start <= self.end)
                or (self.start <= other.end <= self.end)
                or (other.start <= self.start <= other.end)
                or (other.start <= self.end <= other.end)
        )

    def contains(self, other: 'Availability') -> bool:
        """Tests if this availability starts before and ends after the
        other."""
        return self.start <= other.start and self.end >= other.end

    def merge_with(self, other: 'Availability') -> 'Availability':
        """Return a new Availability which spans the range of this one and the
        given one."""

        if not isinstance(other, Availability):
            raise Exception('Please provide an Availability object.')
        if not other.overlaps(self, strict=False):
            raise Exception('Only overlapping Availabilities can be merged.')

        return Availability(
            start=min(self.start, other.start), end=max(self.end, other.end)
        )

    def __or__(self, other: 'Availability') -> 'Availability':
        """Performs the merge operation: ``availability1 | availability2``"""
        return self.merge_with(other)

    def intersect_with(self, other: 'Availability') -> 'Availability':
        """Return a new Availability which spans the range covered both by this
        one and the given one."""

        if not isinstance(other, Availability):
            raise Exception('Please provide an Availability object.')
        if not other.overlaps(self, False):
            raise Exception('Only overlapping Availabilities can be intersected.')

        return Availability(
            start=max(self.start, other.start), end=min(self.end, other.end)
        )

    def __and__(self, other: 'Availability') -> 'Availability':
        """Performs the intersect operation: ``availability1 &
        availability2``"""
        return self.intersect_with(other)

    @classmethod
    def union(cls, availabilities: List['Availability']) -> List['Availability']:
        """Return the minimal list of Availability objects which are covered by
        at least one given Availability."""
        if not availabilities:
            return []

        availabilities = sorted(availabilities, key=lambda a: a.start)
        result = [availabilities[0]]
        availabilities = availabilities[1:]

        for avail in availabilities:
            if avail.overlaps(result[-1], False):
                result[-1] = result[-1].merge_with(avail)
            else:
                result.append(avail)

        return result

    @classmethod
    def _pair_intersection(
            cls,
            availabilities_a: List['Availability'],
            availabilities_b: List['Availability'],
    ) -> List['Availability']:
        """return the list of Availabilities, which are covered by each of the
        given sets."""
        result = []

        # yay for O(b*a) time! I am sure there is some fancy trick to make this faster,
        # but we're dealing with less than 100 items in total, sooo.. ¯\_(ツ)_/¯
        for a in availabilities_a:
            for b in availabilities_b:
                if a.overlaps(b, True):
                    result.append(a.intersect_with(b))

        return result

    @classmethod
    def intersection(
            cls, *availabilitysets: List['Availability']
    ) -> List['Availability']:
        """Return the list of Availabilities which are covered by all of the
        given sets."""

        # get rid of any overlaps and unmerged ranges in each set
        availabilitysets = [cls.union(avialset) for avialset in availabilitysets]
        # bail out for obvious cases (there are no sets given, one of the sets is empty)
        if not availabilitysets:
            return []
        if not all(availabilitysets):
            return []
        # start with the very first set ...
        result = availabilitysets[0]
        for availset in availabilitysets[1:]:
            # ... subtract each of the other sets
            result = cls._pair_intersection(result, availset)
        return result

    class Meta:
        verbose_name = _('Availability')
        verbose_name_plural = _('Availabilities')
        ordering = ['event', 'start']
