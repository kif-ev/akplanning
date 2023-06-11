from datetime import datetime

from django import template
from django.utils.formats import date_format

from AKPlan.templatetags.color_gradients import darken
from AKPlanning import settings

register = template.Library()


@register.filter
def highlight_change_colors(akslot):
    """
    Adjust color to highlight recent changes if needed

    :param akslot: akslot to determine color for
    :type akslot: AKSlot
    :return: color that should be used (either default color of the category or some kind of red)
    :rtype: str
    """
    # Do not highlight in preview mode or when changes occurred before the plan was published
    if akslot.event.plan_hidden or (akslot.event.plan_published_at is not None
                                    and akslot.event.plan_published_at > akslot.updated):
        return akslot.ak.category.color

    seconds_since_update = akslot.seconds_since_last_update

    # Last change long ago? Use default color
    if seconds_since_update > settings.PLAN_MAX_HIGHLIGHT_UPDATE_SECONDS:
        return akslot.ak.category.color

    # Recent change? Calculate gradient blend between red and
    recentness = seconds_since_update / settings.PLAN_MAX_HIGHLIGHT_UPDATE_SECONDS
    return darken("#b71540", recentness)


@register.simple_tag
def timestamp_now(tz):
    """
    Get the current timestamp for the given timezone

    :param tz: timezone to be used for the timestamp
    :return: current timestamp in given timezone
    """
    return date_format(datetime.now().astimezone(tz), "c")
