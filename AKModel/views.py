from django.http import Http404

from AKModel.models import Event


class EventSlugMixin:
    """
    Mixin to handle views with event slugs
    """
    event = None

    def get(self, request, *args, **kwargs):
        # Find event based on event slug
        try:
            self.event = Event.get_by_slug(self.kwargs.get("event_slug", None))
        except Event.DoesNotExist:
            raise Http404
        return super().get(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(object_list=object_list, **kwargs)
        # Add event to context (to make it accessible in templates)
        context["event"] = self.event
        return context


class FilterByEventSlugMixin(EventSlugMixin):
    """
    Mixin to filter different querysets based on a event slug from the request url
    """

    def get_queryset(self):
        # Filter current queryset based on url event slug or return 404 if event slug is invalid
        return super().get_queryset().filter(event=self.event)
