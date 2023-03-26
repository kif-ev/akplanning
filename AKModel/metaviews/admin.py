from abc import ABC, abstractmethod

from django.contrib import admin, messages
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView

from AKModel.forms import AdminIntermediateForm, AdminIntermediateActionForm
from AKModel.models import Event


class EventSlugMixin:
    """
    Mixin to handle views with event slugs
    """
    event = None

    def _load_event(self):
        # Find event based on event slug
        if self.event is None:
            self.event = get_object_or_404(Event, slug=self.kwargs.get("event_slug", None))

    def get(self, request, *args, **kwargs):
        self._load_event()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self._load_event()
        return super().post(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        self._load_event()
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        self._load_event()
        return super().create(request, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        if self.event is None:
            self._load_event()
        return super().dispatch(request, *args, **kwargs)

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


class AdminViewMixin:
    site_url = ''
    title = ''

    def get_context_data(self, **kwargs):
        extra = admin.site.each_context(self.request)
        extra.update(super().get_context_data(**kwargs))

        if self.site_url != '':
            extra["site_url"] = self.site_url
        if self.title != '':
            extra["title"] = self.title

        return extra


class IntermediateAdminView(AdminViewMixin, FormView):
    template_name = "admin/AKModel/action_intermediate.html"
    form_class = AdminIntermediateForm

    def get_preview(self):
        return ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = self.title
        context["preview"] = self.get_preview()
        return context


class WizardViewMixin:
    def get_context_data(self, **kwargs):
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
    form_class = AdminIntermediateActionForm
    entities = None

    def get_queryset(self, pks=None):
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
        pass

    def form_valid(self, form):
        self.entities = self.get_queryset(pks=form.cleaned_data['pks'])
        self.action(form)
        messages.add_message(self.request, messages.SUCCESS, self.success_message)
        return super().form_valid(form)


class LoopActionMixin(ABC):
    def action(self, form):
        self.pre_action()
        for entity in self.entities:
            self.perform_action(entity)
            entity.save()
        self.post_action()

    @abstractmethod
    def perform_action(self, entity):
        pass

    def pre_action(self):
        pass

    def post_action(self):
        pass
