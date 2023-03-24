from django.apps import apps
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import TemplateView, DetailView
from django.utils.translation import gettext_lazy as _

from AKModel.models import Event, AK, AKSlot
from AKPlanning import settings


class DashboardView(TemplateView):
    template_name = 'AKDashboard/dashboard.html'

    @method_decorator(ensure_csrf_cookie)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['events'] = Event.objects.filter(public=True).prefetch_related('dashboardbutton_set')
        return context


class DashboardEventView(DetailView):
    template_name = 'AKDashboard/dashboard_event.html'
    context_object_name = 'event'
    model = Event

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Show feed of recent changes (if activated)
        if settings.DASHBOARD_SHOW_RECENT:
            recent_changes = []

            # Newest AKs
            if apps.is_installed("AKSubmission"):
                submission_changes = AK.history.filter(event=context['event'])[:int(settings.DASHBOARD_RECENT_MAX)]
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

                    recent_changes.append({'icon': icon, 'text': text, 'link': s.instance.detail_url, 'timestamp': s.history_date})

            # Changes in plan
            if apps.is_installed("AKPlan"):
                if not context['event'].plan_hidden:
                    last_changed_slots = AKSlot.objects.select_related('ak').filter(event=context['event'], start__isnull=False).order_by('-updated')[
                                         :int(settings.DASHBOARD_RECENT_MAX)]
                    for changed_slot in last_changed_slots:
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
