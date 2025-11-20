from abc import ABC, abstractmethod

from django.contrib import admin, messages
from django.contrib.admin.models import CHANGE, LogEntry
from django.db.models import Model
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView

from AKModel.forms import AdminIntermediateForm, AdminIntermediateActionForm
from AKModel.models import Event


class EventSlugMixin:
    """
    Mixin to handle views with event slugs

    This will make the relevant event available as self.event in all kind types of requests
    (generic GET and POST views, list views, dispatching, create views)
    """
    # pylint: disable=no-member
    event = None

    def _load_event(self):
        """
        Perform the real loading of the event data (as specified by event_slug in the URL) into self.event
        """
        # Find event based on event slug
        if self.event is None:
            self.event = get_object_or_404(Event, slug=self.kwargs.get("event_slug", None))

    def get(self, request, *args, **kwargs):
        """
        Override GET request handling to perform loading event first
        """
        self._load_event()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """
        Override POST request handling to perform loading event first
        """
        self._load_event()
        return super().post(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        """
        Override list view request handling to perform loading event first
        """
        self._load_event()
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        """
        Override create view request handling to perform loading event first
        """
        self._load_event()
        return super().create(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        """
        Override dispatch which is called in many generic views to perform loading event first
        """
        if self.event is None:
            self._load_event()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, *, object_list=None, **kwargs):
        """
        Override `get_context_data` to make the event information available in the rendering context as `event`. too
        """
        context = super().get_context_data(object_list=object_list, **kwargs)
        # Add event to context (to make it accessible in templates)
        context["event"] = self.event
        return context


class FilterByEventSlugMixin(EventSlugMixin):
    """
    Mixin to filter different querysets based on a event slug from the request url
    """

    def get_queryset(self):
        """
        Get adapted queryset:
        Filter current queryset based on url event slug or return 404 if event slug is invalid
        :return: Queryset
        """
        return super().get_queryset().filter(event=self.event)


class AdminViewMixin:
    """
    Mixin to provide context information needed in custom admin views

    Will either use default information for `site_url` and `title` or allows to set own values for that
    """
    # pylint: disable=too-few-public-methods

    site_url = ''
    title = ''

    def get_context_data(self, **kwargs):
        """
        Extend context
        """
        extra = admin.site.each_context(self.request)
        extra.update(super().get_context_data(**kwargs))

        if self.site_url != '':
            extra["site_url"] = self.site_url
        if self.title != '':
            extra["title"] = self.title

        return extra


class IntermediateAdminView(AdminViewMixin, FormView):
    """
    Metaview: Handle typical "action but with preview and confirmation step before" workflow
    """
    template_name = "admin/AKModel/action_intermediate.html"
    form_class = AdminIntermediateForm

    def get_preview(self):
        """
        Render a preview of the action to be performed.
        Default is empty
        :return: preview (html)
        :rtype: str
        """
        return ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = self.title
        context["preview"] = self.get_preview()
        return context


class WizardViewMixin:
    """
    Mixin to create wizard-like views.
    This visualizes the progress of the user in the creation process and provides the interlinking to the next step

    In the current implementation, the steps of the wizard are hardcoded here,
    hence this mixin can only be used for the event creation wizard
    """
    # pylint: disable=too-few-public-methods
    def get_context_data(self, **kwargs):
        """
        Extend context
        """
        context = super().get_context_data(**kwargs)
        context["wizard_step"] = self.wizard_step
        context["wizard_steps"] = [
            _("Start"),
            _("Settings"),
            _("Event created, Prepare Import"),
            _("Import categories & requirements"),
            _("Activate?"),
            _("Finish")
        ]
        context["wizard_step_text"] = context["wizard_steps"][self.wizard_step - 1]
        context["wizard_steps_total"] = len(context["wizard_steps"])
        return context


class IntermediateAdminActionView(IntermediateAdminView, ABC):
    """
    Abstract base view: Intermediate action view (preview & confirmation see :class:`IntermediateAdminView`)
    for custom admin actions (marking multiple objects in a django admin model instances list with a checkmark and then
    choosing an action from the dropdown).

    This will automatically handle the decoding of the URL encoding of the list of primary keys django does to select
    which objects the action should be run on, then display a preview, perform the action after confirmation and
    redirect again to the object list including display of a confirmation message
    """
    # pylint: disable=no-member
    form_class = AdminIntermediateActionForm
    entities = None
    success_message : str
    confirmation_message : str
    model : Model

    def get_queryset(self, pks=None):
        """
        Get the queryset of objects to perform the action on
        """
        if pks is None:
            pks = self.request.GET['pks']
        return self.model.objects.filter(pk__in=pks.split(","))

    def get_initial(self):
        initial = super().get_initial()
        initial['pks'] = self.request.GET['pks']
        return initial

    def get_preview(self):
        self.entities = self.get_queryset()
        joined_entities = '\n'.join(str(e) for e in self.entities)
        return f"{self.confirmation_message}:\n\n {joined_entities}"

    def get_success_url(self):
        return reverse(f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist")

    @abstractmethod
    def action(self, form):
        """
        The real action to perform
        :param form: form holding the data probably needed for the action
        """

    def form_valid(self, form):
        self.entities = self.get_queryset(pks=form.cleaned_data['pks'])
        self.action(form)
        LogEntry.objects.log_actions(
            user_id=self.request.user.id,
            queryset=self.entities,
            action_flag=CHANGE,
            change_message=self.success_message
        )
        messages.add_message(self.request, messages.SUCCESS, self.success_message)
        return super().form_valid(form)


class LoopActionMixin(ABC):
    """
    Mixin for the typical kind of action where one needs to loop over all elements
    and perform a certain function on each of them

    The action is performed by overriding `perform_action(self, entity)`
    further customization can be reached with the two callbacks `pre_action()` and `post_action()`
    that are called before and after performing the action loop
    """
    def action(self, form):  # pylint: disable=unused-argument
        """
        The real action to perform.
        Will perform the loop, perform the action on each aelement and call the callbacks

        :param form: form holding the data probably needed for the action
        """
        self.pre_action()
        for entity in self.entities:
            self.perform_action(entity)
            entity.save()
        self.post_action()

    @abstractmethod
    def perform_action(self, entity):
        """
        Action to perform on each entity

        :param entity: entity to perform the action on
        """

    def pre_action(self):
        """
        Callback for custom action before loop starts
        """

    def post_action(self):
        """
        Callback for custom action after loop finished
        """
