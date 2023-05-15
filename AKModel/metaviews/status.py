from abc import ABC, abstractmethod
from collections import defaultdict

from django.template import loader
from django.views.generic import TemplateView

from AKModel.metaviews.admin import AdminViewMixin


class StatusWidget(ABC):
    title = "Status Widget"
    actions = []
    status = "primary"

    @property
    @abstractmethod
    def required_context_type(self) -> str:
        """
        Which model/context is needed to render this widget?
        """
        pass

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
        :return: Dictionary containing the rendered/prepared information
        """
        context = self.get_context_data(context)
        return {
            "body": self.render_body(context, request),
            "title": self.render_title(context),
            "actions": self.render_actions(context),
            "status": self.render_status(context),
        }

    def render_title(self, context: {}) -> str:
        """
        Render title for widget based on context

        By default, the title attribute is used without modification
        :param context: Context for rendering
        :return: Rendered title
        """
        return self.title

    def render_status(self, context: {}) -> str:
        """
        Render status for widget based on context

        By default, the status attribute is used without modification
        :param context: Context for rendering
        :return: Rendered title
        """
        return self.status

    @abstractmethod
    def render_body(self, context: {}, request) -> str:
        """
        Render body for widget based on context

        :param context: Context for rendering
        :return: Rendered widget body (HTML)
        """
        pass

    def render_actions(self, context: {}) -> list[dict]:
        """
        Render actions for widget based on context

        By default, all actions specified for this widget are returned without modification

        :param context: Context for rendering
        :return: List of actions
        """
        return [a for a in self.actions]


class TemplateStatusWidget(StatusWidget):
    @property
    @abstractmethod
    def template_name(self) -> str:
        pass

    def render_body(self, context: {}, request) -> str:
        template = loader.get_template(self.template_name)
        return template.render(context, request)


class StatusManager:
    """
    Registry for all status widgets
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
    template_name = "admin/AKModel/status/status.html"

    @property
    @abstractmethod
    def provided_context_type(self) -> str:
        """
        Which model/context is provided by this status view?
        """
        pass

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)

        from AKModel.metaviews import status_manager
        context['widgets'] = [w.render(context, self.request) for w in status_manager.get_by_context_type(self.provided_context_type)]

        return self.render_to_response(context)
