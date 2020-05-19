from django.apps import AppConfig
from django.contrib.admin.apps import AdminConfig


class AkmodelConfig(AppConfig):
    name = 'AKModel'


class AKAdminConfig(AdminConfig):
    default_site = 'AKModel.site.AKAdminSite'
