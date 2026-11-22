from collections import Counter, defaultdict

from django.apps import apps
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import Length, Lower
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.formats import date_format, number_format
from django.utils.translation import gettext_lazy as _, ngettext
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import DetailView, TemplateView

from AKModel.models import AK, AKCategory, AKOwner, AKSlot, Event, Room
from AKPlanning import settings


class DashboardView(TemplateView):
    """
    Index view of dashboard and therefore the main entry point for AKPlanning

    Displays information and buttons for all public events
    """
    template_name = 'AKDashboard/dashboard.html'

    @method_decorator(ensure_csrf_cookie)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Load events and split between active and current/featured events and those that should show smaller below
        context["active_and_current_events"] = []
        context["old_events"] = []
        events = Event.objects.filter(public=True).order_by("-active", "-pk").prefetch_related('dashboardbutton_set')
        for event in events:
            if event.active or len(context["active_and_current_events"]) < settings.DASHBOARD_MAX_FEATURED_EVENTS:
                context["active_and_current_events"].append(event)
            else:
                context["old_events"].append(event)
        context["active_event_count"] = len(context["active_and_current_events"])
        context["old_event_count"] = len(context["old_events"])
        context["total_event_count"] = context["active_event_count"] + context["old_event_count"]
        return context


class DashboardEventView(DetailView):
    """
    Dashboard view for a single event

    In addition to the basic information and the buttons,
    an overview over recent events (new and changed AKs, moved AKSlots) for the given event is shown.

    The event dashboard also exists for non-public events (one only needs to know the URL/slug of the event).
    """
    template_name = 'AKDashboard/dashboard_event.html'
    context_object_name = 'event'
    model = Event

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Show feed of recent changes (if activated)
        if settings.DASHBOARD_SHOW_RECENT:
            # Create a list of chronically sorted events (both AK and plan changes):
            recent_changes = []

            # Newest AKs (if AKSubmission is used)
            if apps.is_installed("AKSubmission"):
                # Get the latest x changes (if there are that many),
                # where x corresponds to the entry threshold configured in the settings
                # (such that the list will be completely filled even if there are no (newer) plan changes)
                submission_changes = AK.history.filter(event=context['event'])[  # pylint: disable=no-member
                    :int(settings.DASHBOARD_RECENT_MAX)]
                # Create textual representation including icons
                for s in submission_changes:
                    if s.history_type == '+':
                        text = _('New AK: %(ak)s.') % {'ak': s.name}
                        icon = ('plus-square', 'far')
                    elif s.history_type == '~':
                        text = _('AK "%(ak)s" edited.') % {'ak': s.name}
                        icon = ('pen-square', 'fas')
                    else:
                        text = _('AK "%(ak)s" deleted.') % {'ak': s.name}
                        icon = ('times', 'fas')

                    # Store representation in change list (still unsorted)
                    recent_changes.append(
                            {'icon': icon, 'text': text, 'link': s.instance.detail_url, 'timestamp': s.history_date}
                    )

            # Changes in plan (if AKPlan is used and plan is publicly visible)
            if apps.is_installed("AKPlan") and not context['event'].plan_hidden:
                # Get the latest plan changes (again using a threshold, see above)
                last_changed_slots = AKSlot.objects.select_related('ak').filter(event=context['event'],
                                                                                start__isnull=False).order_by(
                        '-updated')[:int(settings.DASHBOARD_RECENT_MAX)]  # pylint: disable=line-too-long
                for changed_slot in last_changed_slots:
                    # Create textual representation including icons and links and store in list (still unsorted)
                    recent_changes.append({'icon': ('clock', 'far'),
                                           'text': _('AK "%(ak)s" (re-)scheduled.') % {'ak': changed_slot.ak.name},
                                           'link': changed_slot.ak.detail_url,
                                           'timestamp': changed_slot.updated})

            # Sort by change date...
            recent_changes.sort(key=lambda x: x['timestamp'], reverse=True)
            # ... and restrict to the latest 25 changes
            context['recent_changes'] = recent_changes[:int(settings.DASHBOARD_RECENT_MAX)]
        else:
            context['recent_changes'] = []

        return context


def _fact(icon, title, value, detail="", *, ranking=None, ranking_title=""):
    """
    Create the representation of a single fact for the event info page

    :param icon: font awesome icon as tuple of name and style, e.g., ('crown', 'fas')
    :param title: short description of the fact
    :param value: value of the fact (will be highlighted)
    :param detail: optional further explanation
    :param ranking: optional list of (name, explanation) tuples that will be shown as numbered list below the value
    :param ranking_title: heading of the ranking
    :return: fact representation
    :rtype: dict
    """
    return {'icon': icon, 'title': title, 'value': value, 'detail': detail,
            'ranking': ranking or [], 'ranking_title': ranking_title}


def _format_number(value):
    """
    Format a number for display (localized, without decimal places for whole numbers, otherwise with one)

    :param value: number to format
    :return: formatted number
    :rtype: str
    """
    return number_format(value, decimal_pos=0 if value == int(value) else 1)


def _top_entries(queryset, field):
    """
    Get all entries of a queryset that share the highest (positive) value of the given field

    :param queryset: queryset to search in (usually annotated with the field)
    :param field: name of the field to maximize
    :return: maximum value and list of all entries with that value (0 and empty list if there are no positive values)
    :rtype: (int, list)
    """
    # The field name is only known at runtime, hence the lookups are built as dicts and unpacked as keyword
    # arguments, e.g., for field="ak_count", {f"{field}__gt": 0} becomes filter(ak_count__gt=0).
    # Filtering on an annotated field works because Django turns it into a condition on the aggregate (HAVING).
    # Entries with a value of 0 (e.g., categories without AKs) are dropped since they are no meaningful "top" entry.
    # The remaining entries are sorted descending, so the first one has the highest value.
    # Ties are ordered by name (case-insensitively to get the same order regardless of the database collation).
    queryset = queryset.filter(**{f"{field}__gt": 0}).order_by(f"-{field}", Lower('name'))

    # Fetch only this single entry (LIMIT 1) to determine the highest value.
    # No entry means that there were no entries with a positive value at all
    top = queryset.first()
    if top is None:
        return 0, []
    value = getattr(top, field)

    # There may be ties, so instead of returning only the first entry,
    # query again for all entries with exactly the highest value (a second database query).
    # This returns at least one entry, namely the one fetched above
    return value, list(queryset.filter(**{field: value}))


def _count_institutions(institution_names):
    """
    Count how often each institution occurs, treating different spellings of the same institution as one

    Spellings that only differ in case or surrounding whitespace (e.g., "Uni X" and " uni x") are considered
    the same institution. Empty institution names are ignored.

    :param institution_names: institution names to count (e.g., the institutions of all AK owners of an event)
    :return: list of (display name, count) tuples, ordered by count (descending) and then by display name.
        The display name of an institution is its most common spelling
        (the alphabetically first one if multiple spellings are equally common)
    :rtype: list[(str, int)]
    """
    # Step 1: Group the spellings by institution and count how often each spelling occurs.
    # The normalized name (trimmed and case-insensitive) identifies the institution, e.g.,
    # {"uni x": Counter({"Uni X": 2, "uni x": 1})}
    spellings_per_institution = defaultdict(Counter)
    for name in institution_names:
        spelling = name.strip()
        if spelling == "":
            continue
        normalized_name = spelling.casefold()
        spellings_per_institution[normalized_name][spelling] += 1

    # Step 2: Determine the display name and the total count for each institution
    institutions = []
    for spelling_counts in spellings_per_institution.values():
        # Prefer the most common spelling, in case of a tie the alphabetically first one
        display_name = sorted(spelling_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
        total_count = sum(spelling_counts.values())
        institutions.append((display_name, total_count))

    # Step 3: Order by count (descending), institutions with the same count are ordered by name
    institutions.sort(key=lambda institution: (-institution[1], institution[0]))
    return institutions


class DashboardEventInfoView(DetailView):
    """
    Info page for a single event, showing (trivia) facts about the event

    Most facts are computed from the data of the event, additional facts that cannot be derived
    (e.g., the number of solver runs) can be maintained manually as :class:`AKDashboard.models.EventFact`.

    Like the event dashboard, this page also exists for non-public events (one only needs to know the URL/slug).
    Facts revealing the schedule (or its publication) are only shown if the plan is publicly visible.
    """
    template_name = 'AKDashboard/dashboard_event_info.html'
    context_object_name = 'event'
    model = Event

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        event = context['event']

        # Compute facts, every method returns a (potentially empty) list of facts
        facts = []
        for compute_facts in [self._plan_published_facts, self._ak_count_facts,
                              self._slot_facts, self._category_facts,
                              self._owner_facts, self._ak_name_facts,
                              self._room_facts]:
            facts.extend(compute_facts(event))

        # Add manually maintained facts
        for fact in event.eventfact_set.all():
            icon = (fact.icon.name, fact.icon.style_prefix) if fact.icon else ('circle-info', 'fas')
            facts.append(_fact(icon, fact.title, fact.value))

        context['facts'] = facts
        return context

    @staticmethod
    def _plan_published_facts(event):
        if event.plan_hidden:
            return []
        # Older events may not have a publication timestamp
        if event.plan_published_at is None:
            return [_fact(('calendar-check', 'far'), _("Plan published"), _("Yes"))]
        published_at = timezone.localtime(event.plan_published_at, event.timezone)
        return [_fact(('calendar-check', 'far'), _("Plan published"), date_format(published_at, "DATETIME_FORMAT"))]

    @staticmethod
    def _ak_count_facts(event):
        # Wishes are AKs without owners
        aks = AK.objects.filter(event=event).annotate(owner_count=Count('owners'))
        return [
            _fact(('lightbulb', 'far'), _("AKs"), aks.filter(owner_count__gt=0).count()),
            _fact(('wand-magic-sparkles', 'fas'), _("AK Wishes"), aks.filter(owner_count=0).count()),
        ]

    @staticmethod
    def _slot_facts(event):
        total_duration = AKSlot.objects.filter(event=event).aggregate(total=Sum('duration'))['total']
        if not total_duration:
            return []
        detail = ""
        if total_duration >= 24:
            detail = _("That is %(days)s days without a break") % {'days': _format_number(total_duration / 24)}
        return [_fact(('hourglass-half', 'fas'), _("Hours of AKs in total"), _format_number(total_duration), detail)]

    @staticmethod
    def _owner_facts(event):
        owners = AKOwner.objects.filter(event=event)
        if not owners.exists():
            return []
        facts = []

        # Trashed AKs do not count
        ak_count, top_owners = _top_entries(
                owners.annotate(ak_count=Count('ak', filter=Q(ak__trashed_at__isnull=True))), 'ak_count')
        if top_owners:
            # List the (non-trashed) AKs of the top owners, prefixed with the owner's name if there are multiple
            ak_lists = {owner: ", ".join(owner.ak_set.filter(trashed_at__isnull=True).order_by(Lower('name'))
                                         .values_list('name', flat=True))
                        for owner in top_owners}
            if len(top_owners) == 1:
                detail = ngettext("%(count)s AK: %(aks)s", "%(count)s AKs: %(aks)s", ak_count) % {
                    'count': ak_count, 'aks': ak_lists[top_owners[0]]}
            else:
                detail = ngettext("%(count)s AK each – %(aks)s", "%(count)s AKs each – %(aks)s", ak_count) % {
                    'count': ak_count, 'aks': "; ".join(f"{owner.name}: {aks}" for owner, aks in ak_lists.items())}
            facts.append(_fact(('crown', 'fas'), _("Most AKs by one person"),
                               ", ".join(owner.name for owner in top_owners), detail))

        average_name_length = owners.aggregate(average=Avg(Length('name')))['average']
        facts.append(_fact(('signature', 'fas'), _("Average length of AK owner names"),
                           _format_number(average_name_length),
                           ngettext("character", "characters", round(average_name_length))))

        institutions = _count_institutions(owners.values_list('institution', flat=True))
        if institutions:
            # Top three institutions by number of AK owners (not considering how many AKs they offer)
            ranking = [(name, ngettext("%(count)s AK owner", "%(count)s AK owners", count) % {'count': count})
                       for name, count in institutions[:3]]
            facts.append(_fact(('building-columns', 'fas'), _("Different institutions"), len(institutions),
                               ranking=ranking, ranking_title=_("Institutions with the most AK owners")))
        return facts

    @staticmethod
    def _category_facts(event):
        # Trashed AKs do not count
        categories = AKCategory.objects.filter(event=event).annotate(
                ak_count=Count('ak', filter=Q(ak__trashed_at__isnull=True)))
        ak_count, top_categories = _top_entries(categories, 'ak_count')
        if not top_categories:
            return []
        # Number of AKs for every category (categories with the same number of AKs are ordered by name)
        ranking = [(category.name,
                    ngettext("%(count)s AK", "%(count)s AKs", category.ak_count) % {'count': category.ak_count})
                   for category in categories.order_by('-ak_count', Lower('name'))]
        return [_fact(('layer-group', 'fas'), _("Most popular category"),
                      ", ".join(category.name for category in top_categories),
                      ngettext("%(count)s AK", "%(count)s AKs", ak_count) % {'count': ak_count},
                      ranking=ranking, ranking_title=_("AKs per category"))]

    @staticmethod
    def _ak_name_facts(event):
        aks = AK.objects.filter(event=event).annotate(name_length=Length('name'))
        longest = aks.order_by('-name_length', Lower('name')).first()
        if longest is None:
            return []
        shortest = aks.order_by('name_length', Lower('name')).first()
        return [
            _fact(icon, title, ak.name,
                  ngettext("%(count)s character", "%(count)s characters", ak.name_length) % {'count': ak.name_length})
            for icon, title, ak in [
                (('temperature-empty', 'fas'), _("Shortest AK name"), shortest),
                (('temperature-three-quarters', 'fas'), _("Longest AK name"), longest)
            ]
        ]

    @staticmethod
    def _room_facts(event):
        rooms = Room.objects.filter(event=event)
        if not rooms.exists():
            return []

        # Show the busiest rooms together with the room count,
        # but do not reveal the schedule if the plan is not public yet
        ranking = []
        if not event.plan_hidden:
            # Top three rooms by scheduled hours (only counting scheduled slots),
            # rooms with the same number of hours are ordered by name
            # (slots of trashed AKs are unscheduled when trashing, hence no explicit trash filter is needed here)
            top_rooms = rooms.annotate(
                    scheduled_hours=Sum('akslot__duration', filter=Q(akslot__start__isnull=False))
            ).filter(scheduled_hours__gt=0).order_by('-scheduled_hours', Lower('name'))[:3]
            ranking = [(room.name, _("%(hours)s hours of AKs") % {'hours': _format_number(room.scheduled_hours)})
                       for room in top_rooms]
        return [_fact(('door-open', 'fas'), _("Rooms"), rooms.count(),
                      ranking=ranking, ranking_title=_("Busiest rooms"))]
