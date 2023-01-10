from django import template
from django.apps import apps
from django.conf import settings
from django.utils.html import format_html, mark_safe, conditional_escape
from django.templatetags.static import static
from fontawesome_6.app_settings import get_css

register = template.Library()


# Get Footer Info from settings
@register.simple_tag
def footer_info():
    return settings.FOOTER_INFO


@register.filter
def check_app_installed(name):
    return apps.is_installed(name)


@register.filter
def message_bootstrap_class(tag):
    if tag == "error":
        return "alert-danger"
    elif tag == "success":
        return "alert-success"
    elif tag == "warning":
        return "alert-warning"
    return "alert-info"


@register.filter
def wiki_owners_export(owners, event):
    def to_link(owner):
        if owner.link != '':
            event_link_prefix, _ = event.base_url.rsplit("/", 1)
            link_prefix, link_end = owner.link.rsplit("/", 1)
            if event_link_prefix == link_prefix:
                return f"[[{link_end}|{str(owner)}]]"
            return f"[{owner.link} {str(owner)}]"
        return str(owner)

    return ", ".join(to_link(owner) for owner in owners.all())


css = get_css()


@register.simple_tag
def fontawesome_6_css():
    return mark_safe(conditional_escape('\n').join(format_html(
            '<link href="{}" rel="stylesheet" media="all">', stylesheet) for stylesheet in css))


@register.simple_tag
def fontawesome_6_js():
    return mark_safe(format_html(
        '<script type="text/javascript" src="{}"></script>', static('fontawesome_6/js/django-fontawesome.js')
    ))