from django.apps import AppConfig
from django.contrib.admin.apps import AdminConfig


class AkmodelConfig(AppConfig):
    """
    App configuration (specifies name of the app and registers the general phases and steps for status tracking)
    """
    name = 'AKModel'

    def ready(self):
        # pylint: disable=import-outside-toplevel
        from django.utils.translation import gettext_lazy as _
        from AKModel.status_tracking import status_tracker

        status_tracker.register_phase("configuration", _("Basic configuration"), order=10)
        status_tracker.register_phase("scheduling", _("Plan creation"), order=30)
        status_tracker.register_phase("aftermath", _("Aftermath"), order=50)

        status_tracker.register_step("configuration", "categories", _("Create AK categories"), order=10,
                                     mandatory=True)
        status_tracker.register_step("configuration", "requirements", _("Create requirements"), order=11)
        status_tracker.register_step("configuration", "activate", _("Activate event"), order=90, mandatory=True)
        status_tracker.register_step("aftermath", "wiki_export", _("Transfer AK list to wiki"), order=20)
        status_tracker.register_step("aftermath", "protocols", _("Migrate protocols to wiki"), order=80)
        status_tracker.register_step("aftermath", "deactivate", _("Deactivate event"), order=90, mandatory=True)

        # Connect signal receivers (e.g., for automated status tracking)
        import AKModel.signals  # noqa: F401  # pylint: disable=unused-import


class AKAdminConfig(AdminConfig):
    """
    App configuration for admin
    Loading a custom version here allows to add additional contex and further adapt the behavior of the admin interface
    """
    default_site = 'AKModel.site.AKAdminSite'
