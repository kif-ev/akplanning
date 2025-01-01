from django import template
from django.apps import apps
from django.conf import settings
from django.utils.html import format_html, mark_safe, conditional_escape
from django.templatetags.static import static
from django.template.defaultfilters import date
from fontawesome_6.app_settings import get_css

from AKModel.models import Event

register = template.Library()


@register.simple_tag
def footer_info():
    """
    Get Footer Info from settings

    :return: a dict of several strings like the impress URL to use in the footer
    :rtype: Dict[str, str]
    """
    return settings.FOOTER_INFO


@register.filter
def check_app_installed(name):
    """
    Check whether the app with the given name is active in this instance

    :param name: name of the app to check for
    :return: true if app is installed
    :rtype: bool
    """
    return apps.is_installed(name)


@register.filter
def message_bootstrap_class(tag):
    """
    Turn message severity classes into corresponding bootstrap css classes

    :param tag: severity of the message
    :return: matching bootstrap class
    """
    if tag == "error":
        return "alert-danger"
    if tag == "success":
        return "alert-success"
    if tag == "warning":
        return "alert-warning"
    return "alert-info"


@register.filter
def wiki_owners_export(owners, event):
    """
    Preserve owner link information for wiki export by using internal links if possible
    but external links when owner specified a non-wikilink. This is applied to the full list of owners

    :param owners: list of owners
    :param event: event this owner belongs to and that is currently exported (specifying this directly prevents unnecessary database lookups) #pylint: disable=line-too-long
    :return: linkified owners list in wiki syntax
    :rtype: str
    """
    def to_link(owner):
        if owner.link != '':
            event_link_prefix, _ = event.base_url.rsplit("/", 1)
            link_prefix, link_end = owner.link.rsplit("/", 1)
            if event_link_prefix == link_prefix:
                return f"[[{link_end}|{str(owner)}]]"
            return f"[{owner.link} {str(owner)}]"
        return str(owner)

    return ", ".join(to_link(owner) for owner in owners.all())


@register.filter
def event_month_year(event:Event):
    """
    Print rough event date (month and year)
    :param event: event to print the date for
    :return: string containing rough date information for event
    """
    if event.start.month == event.end.month:
        return f"{date(event.start, 'F')} {event.start.year}"
    event_start_string = date(event.start, 'F')
    if event.start.year != event.end.year:
        event_start_string = f"{event_start_string} {event.start.year}"
    return f"{event_start_string} - {date(event.end, 'F')} {event.end.year}"


# get list of relevant css fontawesome css files for this instance
css = get_css()


@register.simple_tag
def fontawesome_6_css():
    """
    Create html code to load all required fontawesome css files

    :return: HTML code to load css
    :rtype: str
    """
    return mark_safe(conditional_escape('\n').join(format_html(
            '<link href="{}" rel="stylesheet" media="all">', stylesheet) for stylesheet in css))


@register.simple_tag
def fontawesome_6_js():
    """
    Create html code to load all required fontawesome javascript files

    :return: HTML code to load js
    :rtype: str
    """
    return mark_safe(format_html(
        '<script type="text/javascript" src="{}"></script>', static('fontawesome_6/js/django-fontawesome.js')
    ))
