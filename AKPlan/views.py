from datetime import datetime, timedelta

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import DetailView, ListView

from AKModel.metaviews.admin import FilterByEventSlugMixin
from AKModel.models import AKSlot, AKTrack, Room


class PlanIndexView(FilterByEventSlugMixin, ListView):
    """
    Default plan view

    Shows two lists of current and upcoming AKs and a graphical full plan below
    """
    model = AKSlot
    template_name = "AKPlan/plan_index.html"
    context_object_name = "akslots"
    ordering = "start"

    def get_queryset(self):
        # Ignore slots not scheduled yet
        return (super().get_queryset().filter(start__isnull=False).
                select_related('event', 'ak', 'room', 'ak__category', 'ak__event'))
                # Need to prefetch both event and ak__event
                # since django is not aware that the two are always the same

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)

        context["event"] = self.event

        current_timestamp = datetime.now().astimezone(self.event.timezone)

        context["akslots_now"] = []
        context["akslots_next"] = []
        rooms = set()
        buildings = set()

        # Get list of current and next slots
        for akslot in context["akslots"]:
            self._process_slot(akslot)
            # Construct a list of all rooms used by these slots on the fly
            if akslot.room is not None:
                rooms.add(akslot.room)
                # Store buildings for hierarchical view
                if akslot.room.location != '':
                    buildings.add(akslot.room.location)

            # Recent AKs: Started but not ended yet
            if akslot.start <= current_timestamp <= akslot.end:
                context["akslots_now"].append(akslot)
            # Next AKs: Not started yet, list will be filled in order until threshold is reached
            elif akslot.start > current_timestamp:
                if len(context["akslots_next"]) < settings.PLAN_MAX_NEXT_AKS:
                    context["akslots_next"].append(akslot)

        # Sort list of rooms by title
        context["rooms"] = sorted(rooms, key=lambda x: x.title)
        if settings.PLAN_SHOW_HIERARCHY:
            context["buildings"] = sorted(buildings)

        context["tracks"] = self.event.aktrack_set.all()

        return context

    def _process_slot(self, akslot):
        """
        Function to be called for each slot when looping over the slots
        (meant to be overridden in inherited views)

        :param akslot: current slot
        :type akslot: AKSlot
        """


class PlanScreenView(PlanIndexView):
    """
    Plan view optimized for screens and projectors

    This again shows current and upcoming AKs as well as a graphical plan,
    but no navigation elements and trys to use the available space as best as possible
    such that no scrolling is needed.

    The view contains a frontend functionality for auto-reload.
    """
    template_name = "AKPlan/plan_wall.html"

    def get(self, request, *args, **kwargs):
        s = super().get(request, *args, **kwargs)
        # Don't show wall when event is not active -> redirect to normal schedule
        if not self.event.active or (self.event.plan_hidden and not request.user.is_staff):
            return redirect(reverse_lazy("plan:plan_overview", kwargs={"event_slug": self.event.slug}))
        return s

    # pylint: disable=attribute-defined-outside-init
    def get_queryset(self):
        now = datetime.now().astimezone(self.event.timezone)
        # Wall during event: Adjust, show only parts in the future
        if self.event.start < now < self.event.end:
            # Determine interesting range (some hours ago until some hours in the future as specified in the settings)
            self.start = now - timedelta(hours=settings.PLAN_WALL_HOURS_RETROSPECT)
        else:
            self.start = self.event.start
        self.end = self.event.end

        # Restrict AK slots to relevant ones
        # This will automatically filter all rooms not needed for the selected range in the orginal get_context method
        return super().get_queryset().filter(start__gt=self.start)

    def get_context_data(self, *, object_list=None, **kwargs):
        # Find the earliest hour AKs start and end (handle 00:00 as 24:00)
        self.earliest_start_hour = 23
        self.latest_end_hour = 1
        context = super().get_context_data(object_list=object_list, **kwargs)
        context["start"] = self.start
        context["end"] = self.event.end
        context["earliest_start_hour"] = self.earliest_start_hour
        context["latest_end_hour"] = self.latest_end_hour
        return context

    def _process_slot(self, akslot):
        start_hour = akslot.start.astimezone(self.event.timezone).hour
        if start_hour < self.earliest_start_hour:
            # Use hour - 1 to improve visibility of date change
            self.earliest_start_hour = max(start_hour - 1, 0)
        end_hour = akslot.end.astimezone(self.event.timezone).hour
        # Special case: AK starts before but ends after midnight -- show until midnight
        if end_hour < start_hour:
            self.latest_end_hour = 24
        elif end_hour > self.latest_end_hour:
            # Always use hour + 1, since AK may end at :xy and not always at :00
            self.latest_end_hour = min(end_hour + 1, 24)


class PlanRoomView(FilterByEventSlugMixin, DetailView):
    """
    Plan view for a single room
    """
    template_name = "AKPlan/plan_room.html"
    model = Room
    context_object_name = "room"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        # Restrict AKSlot list to the given room
        # while joining AK, room and category information to reduce the amount of necessary SQL queries
        context["slots"] = AKSlot.objects.filter(room=context['room']).select_related('ak', 'ak__category', 'ak__track')
        return context


class PlanTrackView(FilterByEventSlugMixin, DetailView):
    """
    Plan view for a single track
    """
    template_name = "AKPlan/plan_track.html"
    model = AKTrack
    context_object_name = "track"

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        # Restrict AKSlot list to given track
        # while joining AK, room and category information to reduce the amount of necessary SQL queries
        context["slots"] = AKSlot.objects. \
            filter(event=self.event, ak__track=context['track']). \
            select_related('ak', 'room', 'ak__category')
        return context
