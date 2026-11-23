from django.apps import AppConfig


class AkschedulingConfig(AppConfig):
    """
    App configuration (specifies name of the app and registers steps for status tracking)
    """
    name = 'AKScheduling'

    def ready(self):
        # pylint: disable=import-outside-toplevel
        from django.utils.translation import gettext_lazy as _
        from AKModel.status_tracking import status_tracker

        status_tracker.register_step("scheduling", "rooms", _("Create rooms"), order=10, mandatory=True)
