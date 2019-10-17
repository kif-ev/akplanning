from django.http import Http404

from AKModel.models import Event


class FilterByEventSlugMixin:
    """
    Mixin to filter different querysets based on a event slug from the request url
    """
    event = None

    def get_queryset(self):
        # Find event based on event slug
        try:
            self.event = Event.get_by_slug(self.kwargs.get("event_slug", None))
        except Event.DoesNotExist:
            raise Http404

        # Filter current queryset based on url event slug or return 404 if event slug is invalid
        return super().get_queryset().filter(event=self.event)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        # Add event to context (to make it accessible in templates)
        context["event"] = self.event
        return context
