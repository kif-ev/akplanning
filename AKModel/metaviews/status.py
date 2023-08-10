from abc import ABC, abstractmethod
from collections import defaultdict

from django.template import loader
from django.views.generic import TemplateView

from AKModel.metaviews.admin import AdminViewMixin


class StatusWidget(ABC):
    """
    Abstract parent for status page widgets
    """
    title = "Status Widget"
    actions = []
    status = "primary"

    @property
    @abstractmethod
    def required_context_type(self) -> str:
        """
        Which model/context is needed to render this widget?
        """

    def get_context_data(self, context) -> dict:
        """
        Allow to manipulate the context
        :return: context (with or without changes)
        """
        return context

    def render(self, context: {}, request) -> dict:
        """
        Render widget based on context

        :param context: Context for rendering
        :param request: HTTP request, needed for rendering
        :return: Dictionary containing the rendered/prepared information
        """
        context = self.get_context_data(context)
        return {
            "body": self.render_body(context, request),
            "title": self.render_title(context),
            "actions": self.render_actions(context),
            "status": self.render_status(context),
        }

    def render_title(self, context: {}) -> str:  # pylint: disable=unused-argument
        """
        Render title for widget based on context

        By default, the title attribute is used without modification
        :param context: Context for rendering
        :return: Rendered title
        """
        return self.title

    def render_status(self, context: {}) -> str:  # pylint: disable=unused-argument
        """
        Render status for widget based on context

        By default, the status attribute is used without modification
        :param context: Context for rendering
        :return: Rendered title
        """
        return self.status

    @abstractmethod
    def render_body(self, context: {}, request) -> str:  # pylint: disable=unused-argument
        """
        Render body for widget based on context

        :param context: Context for rendering
        :param request: HTTP request (needed for rendering)
        :return: Rendered widget body (HTML)
        """

    def render_actions(self, context: {}) -> list[dict]:  # pylint: disable=unused-argument
        """
        Render actions for widget based on context

        By default, all actions specified for this widget are returned without modification

        :param context: Context for rendering
        :return: List of actions
        """
        return self.actions


class TemplateStatusWidget(StatusWidget):
    """
    A :class:`StatusWidget` that produces its content by rendering a given html template
    """
    @property
    @abstractmethod
    def template_name(self) -> str:
        """
        Configure the template to use
        :return: name of the template to use
        """

    def render_body(self, context: {}, request) -> str:
        """
        Render the body of the widget using the template rendering method from django
        (load and render template using the provided context)

        :param context: context to use for rendering
        :param request: HTTP request (needed by django)
        :return: rendered content (HTML)
        """
        template = loader.get_template(self.template_name)
        return template.render(context, request)


class StatusManager:
    """
    Registry for all status widgets

    Allows to register status widgets using the `@status_manager.register(name="xyz")` decorator
    """
    widgets = {}
    widgets_by_context_type = defaultdict(list)

    def register(self, name: str):
        """
        Call this as
        @status_manager.register(name="xyz")
        to register a status widget

        :param name: name of this widget (only used internally). Has to be unique.
        """
        def _register(widget_class):
            w = widget_class()
            self.widgets[name] = w
            self.widgets_by_context_type[w.required_context_type].append(w)
            return widget_class

        return _register

    def get_by_context_type(self, context_type: str):
        """
        Filter widgets for ones suitable for provided context

        :param context_type: name of the model provided as context
        :return: a list of all matching widgets
        """
        if context_type in self.widgets_by_context_type.keys():
            return self.widgets_by_context_type[context_type]
        return []


class StatusView(ABC, AdminViewMixin, TemplateView):
    """
    Abstract view: A generic base view to create a status page holding multiple widgets
    """
    template_name = "admin/AKModel/status/status.html"

    @property
    @abstractmethod
    def provided_context_type(self) -> str:
        """
        Which model/context is provided by this status view?
        """

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)

        # Load status manager (local import to prevent cyclic import)
        from AKModel.metaviews import status_manager  # pylint: disable=import-outside-toplevel

        # Render all widgets and provide them as part of the context
        context['widgets'] = [w.render(context, self.request)
                              for w in status_manager.get_by_context_type(self.provided_context_type)]

        return self.render_to_response(context)
