from django import template
from django.conf import settings

register = template.Library()

# Get Footer Info from settings
@register.simple_tag
def footer_info():
    return settings.FOOTER_INFO
