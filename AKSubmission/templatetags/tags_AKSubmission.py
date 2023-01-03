from django import template
from fontawesome_6.templatetags.fontawesome_6 import fa6_icon

register = template.Library()


@register.filter
def bool_symbol(bool_val):
    if bool_val:
        return fa6_icon("check", "fas")
    return fa6_icon("times", "fas")


@register.inclusion_tag("AKSubmission/tracks_list.html")
def track_list(tracks, event_slug):
    return {"tracks": tracks, "event_slug": event_slug}


@register.inclusion_tag("AKSubmission/category_list.html")
def category_list(categories, event_slug):
    return {"categories": categories, "event_slug": event_slug}


@register.inclusion_tag("AKSubmission/category_linked_badge.html")
def category_linked_badge(category, event_slug):
    return {"category": category, "event_slug": event_slug}
