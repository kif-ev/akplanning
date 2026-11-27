"""
Scheduling statistics: Number of scheduled AK slots per default slot (overall and per category)
and a simple line chart visualization of these numbers (rendered as SVG, no JavaScript library needed)
"""
import math
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from typing import Any

from AKModel.models import AKSlot, Event

# Fallback colors for categories without (valid) color
_FALLBACK_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f"]
_TOTAL_COLOR = "#212529"


def _category_color(category, index: int) -> str:
    """Get a valid CSS color for the given category (colors may be stored with or without leading #)"""
    return category.css_color or _FALLBACK_COLORS[index % len(_FALLBACK_COLORS)]


def _format_range(event: Event, start, end) -> str:
    """Format a time range in the timezone of the event (localized according to the active language)"""
    start = start.astimezone(event.timezone)
    end = end.astimezone(event.timezone)
    end_format = 'G:i' if start.date() == end.date() else 'D G:i'
    return f"{date_format(start, 'D G:i', use_l10n=True)} - {date_format(end, end_format, use_l10n=True)}"


def scheduling_statistics(event: Event) -> dict:
    """
    Count the scheduled AK slots per default slot, overall and per category

    A scheduled slot is assigned to the default slot it starts in. Slots not starting in any default slot
    are counted as outside of default slots.

    :param event: event to compute the statistics for
    :return: dict containing the categories (with colors), one row per default slot
        (label, total and counts per category in the order of the categories),
        the numbers of slots outside of default slots, the total number of scheduled slots (overall and per category)
        and the number of AKs with intention to submit a resolution
    :rtype: dict
    """
    categories = list(event.akcategory_set.order_by('name'))
    default_slots = list(event.defaultslot_set.order_by('start', 'end'))
    slots = list(AKSlot.objects.filter(event=event, start__isnull=False).select_related('ak'))

    def count_per_category(slot_list):
        return [sum(1 for s in slot_list if s.ak.category_id == c.pk) for c in categories]

    rows = []
    inside: set[int] = set()
    for default_slot in default_slots:
        slots_in_default_slot = [s for s in slots
                                 if default_slot.start <= s.scheduled_start < default_slot.end]
        inside.update(s.pk for s in slots_in_default_slot)
        rows.append({
            "default_slot": default_slot,
            "label": _format_range(event, default_slot.start, default_slot.end),
            "total": len(slots_in_default_slot),
            "per_category": count_per_category(slots_in_default_slot),
        })

    outside = [s for s in slots if s.pk not in inside]
    outside_per_category = count_per_category(outside)
    scheduled_per_category = count_per_category(slots)
    return {
        "categories": [{"category": c, "color": _category_color(c, i)} for i, c in enumerate(categories)],
        "rows": rows,
        "scheduled_per_category": scheduled_per_category,
        "scheduled_by_category": [{"category": c, "count": n} for c, n in zip(categories, scheduled_per_category)],
        "reso_total": event.ak_set.filter(reso=True).count(),
        "outside_total": len(outside),
        "outside_per_category": outside_per_category,
        # Only categories with slots outside of default slots (for display)
        "outside_by_category": [{"category": c, "count": n} for c, n in zip(categories, outside_per_category) if n],
        "scheduled_total": len(slots),
    }


def statistics_line_chart(stats: dict, width: int = 900, height: int = 340) -> dict | None:
    """
    Compute the geometry of a line chart (SVG) for the given statistics:
    One line for the sum over all categories and one line per category

    :param stats: statistics as returned by :func:`scheduling_statistics`
    :param width: width of the chart (SVG units)
    :param height: height of the chart (SVG units)
    :return: chart geometry for the template ``admin/AKScheduling/statistics_chart.html``
        or None if there are no default slots
    :rtype: dict | None
    """
    rows = stats["rows"]
    if not rows:
        return None

    left, right, top, bottom = 45, width - 15, 15, height - 90
    max_value = max([r["total"] for r in rows] + [1])
    # Integer ticks on the y axis (at most about 6)
    step = max(1, math.ceil(max_value / 5))
    y_max = step * math.ceil(max_value / step)

    def x_pos(index):
        if len(rows) == 1:
            return (left + right) / 2
        return left + index * (right - left) / (len(rows) - 1)

    def y_pos(value):
        return bottom - value * (bottom - top) / y_max

    return {
        "width": width,
        "height": height,
        "left": left, "right": right, "top": top, "bottom": bottom,
        "y_ticks": [{"y": round(y_pos(v), 1), "text": str(v)} for v in range(0, y_max + 1, step)],
        "x_labels": [{"x": round(x_pos(i), 1), "y": bottom + 12, "text": r["label"]} for i, r in enumerate(rows)],
        "series": _chart_series(stats, x_pos, y_pos),
    }


def _chart_series(stats: dict, x_pos, y_pos) -> list[dict]:
    """
    Compute the lines of the chart: One for the sum over all categories and one per category

    :param stats: statistics as returned by :func:`scheduling_statistics`
    :param x_pos: function mapping the index of a default slot to the x coordinate
    :param y_pos: function mapping a value to the y coordinate
    :return: list of lines (name, color, width, points and dots with tooltips)
    :rtype: list[dict]
    """
    rows = stats["rows"]
    definitions: list[dict[str, Any]] = [{"name": _("All categories"), "color": _TOTAL_COLOR, "width": 3,
                    "values": [r["total"] for r in rows]}]
    for index, category in enumerate(stats["categories"]):
        definitions.append({"name": str(category["category"]), "color": category["color"], "width": 2,
                            "values": [r["per_category"][index] for r in rows]})

    series = []
    for definition in definitions:
        points = [(round(x_pos(i), 1), round(y_pos(v), 1)) for i, v in enumerate(definition["values"])]
        series.append({
            "name": definition["name"],
            "color": definition["color"],
            "width": definition["width"],
            "points": " ".join(f"{x},{y}" for x, y in points),
            "dots": [{"x": x, "y": y, "title": f"{rows[i]['label']}: {definition['name']} = {definition['values'][i]}"}
                     for i, (x, y) in enumerate(points)],
        })
    return series
