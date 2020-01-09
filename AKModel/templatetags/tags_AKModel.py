from django import template
from django.apps import apps
from django.conf import settings

register = template.Library()


# Get Footer Info from settings
@register.simple_tag
def footer_info():
    return settings.FOOTER_INFO


@register.filter
def check_app_installed(name):
    return apps.is_installed(name)
