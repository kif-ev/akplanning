from django import template
from fontawesome_6.templatetags.fontawesome_6 import fa6_icon

register = template.Library()


@register.filter
def bool_symbol(bool_val):
    """
    Show a nice icon instead of the string true/false
    :param bool_val: boolean value to iconify
    :return: check or times icon depending on the value
    """
    if bool_val:
        return fa6_icon("check", "fas")
    return fa6_icon("times", "fas")


@register.inclusion_tag("AKSubmission/tracks_list.html")
def track_list(tracks, event_slug):
    """
    Generate a clickable list of tracks (one badge per track) based upon the tracks_list template

    :param tracks: tracks to consider
    :param event_slug: slug of this event, required for link creation
    :return: html fragment containing track links
    """
    return {"tracks": tracks, "event_slug": event_slug}


@register.inclusion_tag("AKSubmission/category_list.html")
def category_list(categories, event_slug):
    """
    Generate a clickable list of categories (one badge per category) based upon the category_list template

    :param categories: categories to consider
    :param event_slug: slug of this event, required for link creation
    :return: html fragment containing category links
    """
    return {"categories": categories, "event_slug": event_slug}


@register.inclusion_tag("AKSubmission/category_linked_badge.html")
def category_linked_badge(category, event_slug):
    """
    Generate a clickable category badge based upon the category_linked_badge template
    :param category: category to show/link
    :param event_slug: slug of this event, required for link creation
    :return: html fragment containing badge
    """
    return {"category": category, "event_slug": event_slug}


@register.inclusion_tag("AKSubmission/type_linked_badge.html")
def type_linked_badge(type, event_slug):
    """
    Generate a clickable type badge based upon the type_linked_badge template
    :param type: type to show/link
    :param event_slug: slug of this event, required for link creation
    :return: html fragment containing badge
    """
    return {"type": type, "event_slug": event_slug}
