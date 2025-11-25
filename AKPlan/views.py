import json
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import DetailView, ListView
from django.utils.translation import gettext_lazy as _

from AKModel.metaviews.admin import FilterByEventSlugMixin
from AKModel.models import AKSlot, AKTrack, Room, AKType
from AKPlan.templatetags.tags_AKPlan import highlight_change_colors


class PlanIndexView(FilterByEventSlugMixin, ListView):
    """
    Default plan view

    Shows two lists of current and upcoming AKs and a graphical full plan below
    """
    model = AKSlot
    template_name = "AKPlan/plan_index.html"
    context_object_name = "akslots"
    ordering = "start"
    types_filter = None
    query_string = ""

    def get(self, request, *args, **kwargs):
        if 'types' in request.GET:
            try:
                # Initialize types filter, has to be done here such that it is not reused across requests
                self.types_filter = {
                    "yes": [],
                    "no": [],
                    "no_set": set(),
                    "strict": False,
                    "empty": False,
                }
                # If types are given, filter the queryset accordingly
                types_raw = request.GET['types'].split(',')
                for t in types_raw:
                    type_slug, type_condition = t.split(':')
                    if type_condition in ["yes", "no"]:
                        t = AKType.objects.get(slug=type_slug, event=self.event)
                        self.types_filter[type_condition].append(t)
                        if type_condition == "no":
                            # Store slugs of excluded types in a set for faster lookup
                            self.types_filter["no_set"].add(t.slug)
                    else:
                        raise ValueError(f"Unknown type condition: {type_condition}")
                if 'strict' in request.GET:
                    # If strict is specified and marked as "yes",
                    # exclude all AKs that have any of the excluded types ("no"),
                    # even if they have other types that are marked as "yes"
                    self.types_filter["strict"] = request.GET.get('strict') == 'yes'
                if 'empty' in request.GET:
                    # If empty is specified and marked as "yes", include AKs that have no types at all
                    self.types_filter["empty"] = request.GET.get('empty') == 'yes'
                # Will be used for generating a link to the wall view with the same filter
                self.query_string = request.GET.urlencode(safe=",:")
            except (ValueError, AKType.DoesNotExist):
                # Display an error message if the types parameter is malformed
                messages.add_message(request, messages.ERROR, _("Invalid type filter"))
                self.types_filter = None
        s = super().get(request, *args, **kwargs)
        return s

    def get_queryset(self):
        # Ignore slots not scheduled yet
        qs = (super().get_queryset().filter(start__isnull=False).
                select_related('event', 'ak', 'room', 'ak__category', 'ak__event'))
                # Need to prefetch both event and ak__event
                # since django is not aware that the two are always the same

        # Apply type filter if necessary
        if self.types_filter:
            # Either include all AKs with the given types or without any types at all
            if self.types_filter["empty"]:
                qs = qs.filter(Q(ak__types__in=self.types_filter["yes"]) | Q(ak__types__isnull=True)).distinct()
            # Or only those with the given types
            else:
                qs = qs.filter(ak__types__in=self.types_filter["yes"]).distinct()
            # Afterwards, if strict, exclude all AKs that have any of the excluded types,
            # even though they were included by the previous filter
            if self.types_filter["strict"]:
                qs = qs.exclude(ak__types__in=self.types_filter["no"]).distinct()
        return qs

    def _encode_events(self, akslots):
        """
        Encode events in a format understandable for fullcalendar
        :param akslots: Slots to encode
        :type akslots: Iterable[AKSlot]
        :return: List of dicts in the correct format
        :rtype: List[Dict[str, str]]
        """
        encoded_events = [
                {
                    'title': slot.ak.short_name,
                    'description': slot.ak.name,
                    'start': timezone.localtime(slot.start, self.event.timezone).strftime("%Y-%m-%d %H:%M:%S"),
                    'end': timezone.localtime(slot.end, self.event.timezone).strftime("%Y-%m-%d %H:%M:%S"),
                    'resourceId': slot.room.title,
                    'backgroundColor': highlight_change_colors(slot),
                    'borderColor': slot.ak.category.color,
                    'url': str(slot.ak.detail_url),
                }
                for slot in akslots
                if slot.start and slot.room is not None
            ]
        return encoded_events

    def _encode_rooms(self, rooms):
        """
        Encode rooms (resources) in a format understandable for fullcalendar
        :param rooms: Rooms to encode
        :type rooms: Iterable[Room]
        :return: List of dicts in the correct format
        :rtype: List[Dict[str, str]]
        """
        return [
            {
                'id': room.title,
                'title': room.title,
                'parentId': room.location,
            }
            for room in rooms
        ]

    def _encode_buildings(self, buildings):
        """
        Encode buildings (resources) in a format understandable for fullcalendar
        :param buildings: Buildings to encode
        :type buildings: Iterable[str]
        :return: List of dicts in the correct format
        :rtype: List[Dict[str, str]]
        """
        return [
            {
                'id': building,
                'title': building,
            }
            for building in buildings
        ]

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

        context["categories"] = self.event.akcategory_set.all()
        context["tracks"] = self.event.aktrack_set.all()

        # Pass query string to template for generating a matching wall link
        context["query_string"] = self.query_string

        # Generate a list of all types and their current selection state for graphic filtering
        types = [{"name": t.name, "slug": t.slug, "state": True} for t in self.event.aktype_set.all()]
        if len(types) > 0:
            context["type_filtering_active"] = True
            if self.types_filter:
                for t in types:
                    if t["slug"] in self.types_filter["no_set"]:
                        t["state"] = False
            # Pass type list as well as filter state for strict filtering and empty types to the template
            context["types"] = json.dumps(types)
            context["types_filter_strict"] = False
            context["types_filter_empty"] = False
            if self.types_filter:
                context["types_filter_empty"] = self.types_filter["empty"]
                context["types_filter_strict"] = self.types_filter["strict"]#
        else:
            context["type_filtering_active"] = False

        context["akslots_encoded"] = self._encode_events(context["akslots"])
        context["rooms_encoded"] = self._encode_rooms(context["rooms"])
        context["buildings_encoded"] = self._encode_buildings(context["buildings"])

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

        # Show rooms as flat list without hierarchy (location only as part of the room title)
        for r in context["rooms_encoded"]:
            del r['parentId']

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


class PlanCategoryView(PlanIndexView):
    """
    Plan view restricted to a category
    """
    template_name = "AKPlan/plan_category.html"

    def get_queryset(self):
        # Restrict AK slots to given category
        return super().get_queryset().filter(ak__category__pk=self.kwargs['category'])

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context["category"] = self.event.akcategory_set.get(pk=self.kwargs['category'])
        return context


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
