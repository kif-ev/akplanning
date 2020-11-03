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
