from datetime import datetime

from django import template
from django.utils.formats import date_format

from AKPlan.templatetags.color_gradients import darken
from AKPlanning import settings

register = template.Library()


def recently_changed(akslot) -> bool:
    """
    Check whether the given slot was changed (i.e., added or moved) recently and the change should be highlighted

    :param akslot: akslot to check
    :type akslot: AKSlot
    :return: True if the slot was changed within the highlight period (see PLAN_MAX_HIGHLIGHT_UPDATE_SECONDS)
    :rtype: bool
    """
    # Do not highlight in preview mode or when changes occurred before the plan was published
    if akslot.event.plan_hidden or (akslot.event.plan_published_at is not None
                                    and akslot.event.plan_published_at > akslot.updated):
        return False
    return akslot.seconds_since_last_update <= settings.PLAN_MAX_HIGHLIGHT_UPDATE_SECONDS


@register.filter
def highlight_change_colors(akslot):
    """
    Adjust color to highlight recent changes if needed

    :param akslot: akslot to determine color for
    :type akslot: AKSlot
    :return: color that should be used (either default color of the category or some kind of red)
    :rtype: str
    """
    # No recent change? Use default color
    if not recently_changed(akslot):
        return akslot.ak.category.color

    # Recent change? Calculate gradient blend between red and
    recentness = akslot.seconds_since_last_update / settings.PLAN_MAX_HIGHLIGHT_UPDATE_SECONDS
    return darken("#b71540", recentness)


@register.simple_tag
def timestamp_now(tz):
    """
    Get the current timestamp for the given timezone

    :param tz: timezone to be used for the timestamp
    :return: current timestamp in given timezone
    """
    return date_format(datetime.now().astimezone(tz), "c")
