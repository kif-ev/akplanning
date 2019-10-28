from django.urls import reverse_lazy
from django.views.generic import RedirectView

from AKModel.models import Event


class TopLevelRedirectView(RedirectView):
    is_permanent = False

    def get_redirect_url(self, *args, **kwargs):
        return reverse_lazy('submit:submission_overview',
                       kwargs={'event_slug': Event.objects.filter(active=True).last().slug})
