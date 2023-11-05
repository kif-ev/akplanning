from django.contrib.admin import AdminSite
from django.utils.translation import gettext_lazy as _
# from django.urls import path

from AKModel.models import Event


class AKAdminSite(AdminSite):
    """
    Custom admin interface definition (extend the admin functionality of Django)
    """
    index_template = "admin/ak_index.html"
    site_header = f"AKPlanning - {_('Administration')}"
    index_title = _('Administration')

    def get_urls(self):
        """
        Get URLs -- add further views that are not related to a certain model here if needed
        """
        urls = super().get_urls()
        urls += [
            # path('...', self.admin_view(...)),
        ]
        return urls

    def index(self, request, extra_context=None):
        # Override index page rendering to provide extra context (the list of active events)
        # to be used in the adapted template
        if extra_context is None:
            extra_context = {}
        extra_context["active_events"] = Event.objects.filter(active=True)
        return super().index(request, extra_context)
