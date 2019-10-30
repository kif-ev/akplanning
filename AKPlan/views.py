from django.views.generic import TemplateView

from AKModel.views import EventSlugMixin


class PlanView(EventSlugMixin, TemplateView):
    template_name = 'AKPlan/plan.html'
