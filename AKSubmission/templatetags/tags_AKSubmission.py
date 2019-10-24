from django import template
from fontawesome.templatetags.fontawesome import fontawesome_icon

register = template.Library()


@register.filter
def bool_symbol(bool_val):
    if bool_val:
        return fontawesome_icon("check")
    return fontawesome_icon("times")


@register.inclusion_tag("AKSubmission/tags_list.html")
def tag_list(tags, event_slug):
    return {"tags": tags, "event_slug": event_slug}


@register.inclusion_tag("AKSubmission/category_list.html")
def category_list(categories, event_slug):
    return {"categories": categories, "event_slug": event_slug}


@register.inclusion_tag("AKSubmission/category_linked_badge.html")
def category_linked_badge(category, event_slug):
    return {"category": category, "event_slug": event_slug}


@register.filter
def message_bootstrap_class(tag):
    print(tag)
    if tag == "error":
        return "alert-danger"
    elif tag == "success":
        return "alert-success"
    elif tag == "warning":
        return "alert-warning"
    return "alert-info"
