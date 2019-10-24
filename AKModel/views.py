from django.shortcuts import get_object_or_404

from AKModel.models import Event


class EventSlugMixin:
    """
    Mixin to handle views with event slugs
    """
    event = None

    def _load_event(self):
        # Find event based on event slug
        self.event = get_object_or_404(Event, slug=self.kwargs.get("event_slug", None))

    def get(self, request, *args, **kwargs):
        self._load_event()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self._load_event()
        return super().post(request, *args, **kwargs)

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
