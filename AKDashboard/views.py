from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import TemplateView

from AKModel.models import Event


class DashboardView(TemplateView):
    template_name = 'AKDashboard/dashboard.html'

    @method_decorator(ensure_csrf_cookie)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['events'] = Event.objects.all()
        return context
