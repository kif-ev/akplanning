from datetime import timedelta

from django.conf import settings
from django.utils.datetime_safe import datetime
from django.views.generic import ListView

from AKModel.models import AKSlot
from AKModel.views import FilterByEventSlugMixin


class PlanIndexView(FilterByEventSlugMixin, ListView):
    model = AKSlot
    template_name = "AKPlan/plan_index.html"
    context_object_name = "akslots"
    ordering = "start"

    def get_queryset(self):
        # Ignore slots not scheduled yet
        return super().get_queryset().filter(start__isnull=False)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)

        context["event"] = self.event

        current_timestamp = datetime.now().astimezone(self.event.timezone)

        context["akslots_now"] = []
        context["akslots_next"] = []
        rooms = set()

        # Get list of current and next slots
        for akslot in context["akslots"]:
            # Construct a list of all rooms used by these slots on the fly
            if akslot.room is not None:
                rooms.add(akslot.room)

            # Recent AKs: Started but not ended yet
            if akslot.start <= current_timestamp <= akslot.end:
                context["akslots_now"].append(akslot)
            # Next AKs: Not started yet, list will be filled in order until threshold is reached
            elif akslot.start > current_timestamp:
                if len(context["akslots_next"]) < settings.PLAN_MAX_NEXT_AKS:
                    context["akslots_next"].append(akslot)

        # Sort list of rooms by title
        context["rooms"] = sorted(rooms, key=lambda x: x.title)

        return context


class PlanScreenView(PlanIndexView):
    template_name = "AKPlan/plan_wall.html"

    def get_queryset(self):
        # Determine interesting range (some hours ago until some hours in the future as specified in the settings)
        self.start = datetime.now().astimezone(self.event.timezone) - timedelta(hours=settings.PLAN_WALL_HOURS_RETROSPECT)
        self.end = self.start + timedelta(hours=(settings.PLAN_WALL_HOURS_RETROSPECT + settings.PLAN_WALL_HOURS_FUTURE))

        # Restrict AK slots to relevant ones
        # This will automatically filter all rooms not needed for the selected range in the orginal get_context method
        return super().get_queryset().filter(start__gt=self.start, start__lt=self.end)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        context["start"] = self.start
        context["end"] = self.end
        return context
