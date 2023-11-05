from django.apps import AppConfig
from django.contrib.admin.apps import AdminConfig


class AkmodelConfig(AppConfig):
    """
    App configuration (default, only specifies name of the app)
    """
    name = 'AKModel'


class AKAdminConfig(AdminConfig):
    """
    App configuration for admin
    Loading a custom version here allows to add additional contex and further adapt the behavior of the admin interface
    """
    default_site = 'AKModel.site.AKAdminSite'
