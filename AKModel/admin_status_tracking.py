"""
Admin interface for status tracking (see :mod:`AKModel.status_tracking`)

This module is imported at the end of :mod:`AKModel.admin` to register the admin classes
"""
from django.contrib import admin
from django.contrib.admin import display, SimpleListFilter
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _

from AKModel.admin import EventTimezoneFormMixin, PrepopulateWithNextActiveEventMixin
from AKModel.forms import StatusTrackingEntryAdminForm
from AKModel.models import StatusTrackingEntry
from AKModel.status_tracking import status_tracker


class StatusTrackingPhaseFilter(SimpleListFilter):
    """
    Filter status tracking entries by their phase (showing the names of the registered phases)
    """
    title = _("Phase")
    parameter_name = "phase"

    def lookups(self, request, model_admin):
        return [(p.key, p.name) for p in status_tracker.get_phases()]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(phase=self.value())
        return queryset


@admin.register(StatusTrackingEntry)
class StatusTrackingEntryAdmin(EventTimezoneFormMixin, PrepopulateWithNextActiveEventMixin, admin.ModelAdmin):
    """
    Admin interface for status tracking entries
    Uses an adapted form (see :class:`StatusTrackingEntryAdminForm`) and the timezone of the associated event
    """
    form = StatusTrackingEntryAdminForm
    list_display = ['timestamp_display', 'phase_display', 'step_display', 'mandatory_display', 'progress', 'detail',
                    'event']
    list_filter = ['event', StatusTrackingPhaseFilter, 'progress']
    list_select_related = ['event']
    search_fields = ['step', 'detail']
    date_hierarchy = 'timestamp'

    @display(description=_("Timestamp"), ordering='timestamp')
    def timestamp_display(self, obj: StatusTrackingEntry):
        """
        Show the timestamp in the timezone of the associated event
        """
        local_timestamp = timezone.localtime(obj.timestamp, obj.event.timezone)
        return f"{date_format(local_timestamp, 'SHORT_DATE_FORMAT')} {date_format(local_timestamp, 'H:i')}"

    @staticmethod
    def _registered(getter, fallback):
        """
        Look up information about a registered phase or step, use the fallback if it is not registered (anymore)
        """
        try:
            return getter()
        except KeyError:
            return fallback

    @display(description=_("Phase"), ordering='phase')
    def phase_display(self, obj: StatusTrackingEntry):
        """
        Show the name of the phase (or its key if it is not registered)
        """
        return self._registered(lambda: status_tracker.get_phase(obj.phase).name, obj.phase)

    @display(description=_("Step"), ordering='step')
    def step_display(self, obj: StatusTrackingEntry):
        """
        Show the name of the step (or its key if it is not registered)
        """
        return self._registered(lambda: status_tracker.get_step(obj.phase, obj.step).name, obj.step)

    @display(description=_("Mandatory"), boolean=True)
    def mandatory_display(self, obj: StatusTrackingEntry):
        """
        Show whether the step is mandatory (unknown for steps that are not registered)
        """
        return self._registered(lambda: status_tracker.get_step(obj.phase, obj.step).mandatory, None)
