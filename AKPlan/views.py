import json
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib import messages
from django.db.models import Max, Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, ListView

from AKModel.metaviews.admin import FilterByEventSlugMixin
from AKModel.models import AKSlot, AKTrack, AKType, Room
from AKPlan.templatetags.tags_AKPlan import highlight_change_colors, recently_changed


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
    # Daily range of hours shown in the timeline, determined based on the slots if not set before
    earliest_start_hour = None
    latest_end_hour = None

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

    def _encode_markers(self):
        """
        Encode markers for important points in time of the event (e.g., the resolution deadline)
        as background events in a format understandable for fullcalendar.
        Background events without resource are shown for all resources, the marker is displayed as vertical line
        (see AKPlan/timeline_markers.html)

        :return: List of dicts in the correct format
        :rtype: List[Dict[str, str]]
        """
        markers = []
        if self.event.reso_deadline:
            deadline = timezone.localtime(self.event.reso_deadline, self.event.timezone)
            markers.append({
                'title': '',
                'description': str(_('Resolution Deadline')),
                'start': deadline.strftime("%Y-%m-%d %H:%M:%S"),
                # Short duration, the visible width is determined by the line (border) of the marker
                'end': (deadline + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S"),
                'display': 'background',
                'classNames': ['reso-deadline-marker'],
            })
        return markers

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
            # Next AKs: Not started yet (in order of their start)
            elif akslot.start > current_timestamp:
                context["akslots_next"].append(akslot)

        # Restrict the list of next AKs: Show at least PLAN_MAX_NEXT_AKS, but if the list is shown next to the list
        # of current AKs (on wider screens), it may be as long as that list. Entries beyond PLAN_MAX_NEXT_AKS are hidden
        # on smaller screens in the template
        context["plan_max_next_aks"] = settings.PLAN_MAX_NEXT_AKS
        context["akslots_next"] = context["akslots_next"][
                                  :max(settings.PLAN_MAX_NEXT_AKS, len(context["akslots_now"]))]

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
                context["types_filter_strict"] = self.types_filter["strict"]  #
        else:
            context["type_filtering_active"] = False

        context["akslots_encoded"] = self._encode_events(context["akslots"]) + self._encode_markers()
        context["rooms_encoded"] = self._encode_rooms(context["rooms"])
        context["buildings_encoded"] = self._encode_buildings(context["buildings"])

        # Only show the hours of the day in which slots take place (e.g., hide nights without slots)
        self._determine_visible_hours(context["akslots"])
        context["earliest_start_hour"] = self.earliest_start_hour
        context["latest_end_hour"] = self.latest_end_hour

        return context

    def _process_slot(self, akslot):
        """
        Function to be called for each slot when looping over the slots
        (meant to be overridden in inherited views)

        :param akslot: current slot
        :type akslot: AKSlot
        """

    def _determine_visible_hours(self, akslots):
        """
        Determine the daily range of hours shown in the timeline (slotMinTime/slotMaxTime)
        such that all given slots are visible.
        If the range was already determined before (e.g., by a view based on a different set of slots), keep it.

        :param akslots: slots to consider
        :type akslots: Iterable[AKSlot]
        """
        if self.earliest_start_hour is not None:
            return
        self.earliest_start_hour = 23
        self.latest_end_hour = 1
        for akslot in akslots:
            self._update_visible_hours(akslot)
        # No slots? Show complete days
        if self.earliest_start_hour >= self.latest_end_hour:
            self.earliest_start_hour = 0
            self.latest_end_hour = 24

    def _update_visible_hours(self, akslot):
        """
        Extend the daily range of hours shown in the plan such that the given slot is visible
        (handle 00:00 as 24:00)

        :param akslot: slot to consider
        :type akslot: AKSlot
        """
        start_hour = akslot.start.astimezone(self.event.timezone).hour
        if start_hour < self.earliest_start_hour:
            # Use hour - 1 to improve visibility of date change
            self.earliest_start_hour = max(start_hour - 1, 0)
        end_hour = akslot.end.astimezone(self.event.timezone).hour
        # Special case: AK starts before but ends after midnight -- show until midnight
        if end_hour < start_hour:
            self.latest_end_hour = 24
        elif end_hour + 1 > self.latest_end_hour:
            # Always use hour + 1, since AK may end at :xy and not always at :00
            self.latest_end_hour = min(end_hour + 1, 24)


class PlanScreenView(PlanIndexView):
    """
    Plan view optimized for screens and projectors

    This again shows current and upcoming AKs as well as a graphical plan,
    but no navigation elements and trys to use the available space as best as possible
    such that no scrolling is needed.

    Recently added or moved slots (that did not end yet) are announced in a ticker at the bottom of the page.

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
        event_running = self.event.start < now < self.event.end
        if event_running:
            # Determine interesting range (some hours ago until some hours in the future as specified in the settings)
            self.start = now - timedelta(hours=settings.PLAN_WALL_HOURS_RETROSPECT)
        else:
            self.start = self.event.start
        self.end = self.event.end

        # Restrict AK slots to relevant ones, i.e., those that did not end before the start of the shown range
        # (including slots that started earlier but are still running or ended only recently)
        # The end is not stored in the database, hence first restrict to candidates based on the longest slot
        # and then filter by the real end
        qs = super().get_queryset()
        longest = qs.aggregate(longest=Max('duration'))['longest'] or 0
        candidates = qs.filter(start__gt=self.start - timedelta(hours=float(longest)))
        qs = qs.filter(pk__in=[s.pk for s in candidates.select_related(None).only('start', 'duration')
                               if s.end > self.start])

        # Determine the daily range of hours shown in the plan (based on all remaining slots,
        # so that the range stays stable independent of the further restriction below)
        self._determine_visible_hours(qs.select_related(None).only('start', 'duration'))

        # Further restrict to slots starting within the next visible hours,
        # since slots further in the future would only be reachable by horizontal scrolling anyway.
        # This will automatically filter all rooms not needed for the selected range in the orginal get_context method
        # Only apply this during the event, before and afterwards, the full wall is shown
        self.cutoff = None
        if event_running:
            self.cutoff = self._visible_hours_cutoff(now, settings.PLAN_WALL_VISIBLE_HOURS_AHEAD)
        if self.cutoff is not None:
            qs = qs.filter(start__lt=self.cutoff)
        return qs

    def _visible_hours_cutoff(self, reference, hours):
        """
        Compute the point in time after which the given amount of visible hours have passed, starting at reference.
        Only hours within the daily range shown by the plan (earliest_start_hour to latest_end_hour) are counted,
        hidden hours (e.g., during the night) are skipped.

        :param reference: point in time to start counting from
        :type reference: datetime
        :param hours: amount of visible hours
        :type hours: int
        :return: cutoff point in time or None if no restriction is possible/necessary
        :rtype: datetime | None
        """
        if self.earliest_start_hour >= self.latest_end_hour:
            return None
        tz = self.event.timezone
        cursor = reference.astimezone(tz)
        remaining = timedelta(hours=hours)
        while cursor < self.end:
            day = cursor.date()
            window_start = datetime.combine(day, datetime.min.time(), tzinfo=tz) \
                + timedelta(hours=self.earliest_start_hour)
            window_end = datetime.combine(day, datetime.min.time(), tzinfo=tz) \
                + timedelta(hours=self.latest_end_hour)
            cursor = max(cursor, window_start)
            if cursor < window_end:
                available = window_end - cursor
                if available >= remaining:
                    return cursor + remaining
                remaining -= available
            # Continue at the start of the visible range of the next day
            cursor = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=tz) \
                + timedelta(hours=self.earliest_start_hour)
        return None

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)

        # Lists of current and next AKs are always shown below each other, hence apply the fixed limit
        context["akslots_next"] = context["akslots_next"][:settings.PLAN_MAX_NEXT_AKS]

        # Show rooms as flat list without hierarchy (location only as part of the room title)
        for r in context["rooms_encoded"]:
            del r['parentId']

        # Recently added or moved slots that did not end yet
        # (ordered by start time of the slots which is also the default order of AKSlots, so no need to reorder)
        now = timezone.now()
        context["akslots_changed"] = [s for s in context["akslots"] if s.end > now and recently_changed(s)]

        # Start the plan early enough to completely show slots that started before but are still relevant
        context["start"] = min([self.start] + [s.start for s in context["akslots"]])
        # Only show the plan until the cutoff of the visible hours (but never beyond the end of the event).
        # Extend the range if necessary such that slots starting before but ending after the cutoff are not clipped
        end = self.event.end
        if self.cutoff is not None:
            end = max([self.cutoff] + [s.end for s in context["akslots"]])
            end = min(end, self.event.end)
        context["end"] = end
        return context


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
