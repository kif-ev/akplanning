from django import template

from AKPlan.templatetags.color_gradients import darken
from AKPlanning import settings

register = template.Library()


@register.filter
def highlight_change_colors(akslot):
    seconds_since_update = akslot.seconds_since_last_update

    # Last change long ago? Use default color
    if seconds_since_update > settings.PLAN_MAX_HIGHLIGHT_UPDATE_SECONDS:
        return akslot.ak.category.color

    # Recent change? Calculate gradient blend between red and
    recentness = seconds_since_update / settings.PLAN_MAX_HIGHLIGHT_UPDATE_SECONDS
    return darken("#b71540", recentness)
    # return linear_blend("#b71540", "#000000", recentness)
