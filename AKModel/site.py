from django.contrib.admin import AdminSite
from django.utils.translation import gettext_lazy as _

from AKModel.models import Event


class AKAdminSite(AdminSite):
    index_template = "admin/ak_index.html"
    site_header = f"AKPlanning - {_('Administration')}"
    index_title = _('Administration')

    def get_urls(self):
        from django.urls import path

        urls = super().get_urls()
        urls += [
            # path('...', self.admin_view(...)),
        ]
        return urls

    def index(self, request, extra_context=None):
        if extra_context is None:
            extra_context = {}
        extra_context["active_events"] = Event.objects.filter(active=True)
        return super().index(request, extra_context)
