from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import RedirectView, TemplateView

from AKModel.models import Event


class TopLevelRedirectView(RedirectView):
    is_permanent = False

    def get_redirect_url(self, *args, **kwargs):
        return reverse_lazy('submit:submission_overview',
                            kwargs={'event_slug': Event.objects.filter(active=True).last().slug})


class DashboardView(TemplateView):
    template_name = 'AKDashboard/dashboard.html'

    @method_decorator(ensure_csrf_cookie)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['events'] = Event.objects.all()
        context['event'] = Event.objects.filter(active=True).last()
        return context
