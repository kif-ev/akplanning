from django.apps import apps
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import TemplateView, DetailView
from django.utils.translation import gettext_lazy as _

from AKModel.models import Event, AK, AKSlot
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
                submission_changes = AK.history.filter(event=context['event'])[:int(settings.DASHBOARD_RECENT_MAX)] # pylint: disable=no-member, line-too-long
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
                last_changed_slots = AKSlot.objects.select_related('ak').filter(event=context['event'], start__isnull=False).order_by('-updated')[:int(settings.DASHBOARD_RECENT_MAX)] #pylint: disable=line-too-long
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
