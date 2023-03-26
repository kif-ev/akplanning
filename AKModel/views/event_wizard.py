from django.apps import apps
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, FormView, UpdateView, DetailView

from AKModel.forms import NewEventWizardStartForm, NewEventWizardSettingsForm, NewEventWizardPrepareImportForm, \
    NewEventWizardImportForm, NewEventWizardActivateForm
from AKModel.metaviews.admin import AdminViewMixin, WizardViewMixin, EventSlugMixin
from AKModel.models import Event


class NewEventWizardStartView(AdminViewMixin, WizardViewMixin, CreateView):
    model = Event
    form_class = NewEventWizardStartForm
    template_name = "admin/AKModel/event_wizard/start.html"
    wizard_step = 1


class NewEventWizardSettingsView(AdminViewMixin, WizardViewMixin, CreateView):
    model = Event
    form_class = NewEventWizardSettingsForm
    template_name = "admin/AKModel/event_wizard/settings.html"
    wizard_step = 2

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["timezone"] = context["form"].cleaned_data["timezone"]
        return context

    def get_success_url(self):
        return reverse_lazy("admin:new_event_wizard_prepare_import", kwargs={"event_slug": self.object.slug})


class NewEventWizardPrepareImportView(WizardViewMixin, EventSlugMixin, FormView):
    form_class = NewEventWizardPrepareImportForm
    template_name = "admin/AKModel/event_wizard/created_prepare_import.html"
    wizard_step = 3

    def form_valid(self, form):
        # Selected a valid event to import from? Use this to go to next step of wizard
        return redirect("admin:new_event_wizard_import", event_slug=self.event.slug,
                        import_slug=form.cleaned_data["import_event"].slug)


class NewEventWizardImportView(EventSlugMixin, WizardViewMixin, FormView):
    form_class = NewEventWizardImportForm
    template_name = "admin/AKModel/event_wizard/import.html"
    wizard_step = 4

    def get_initial(self):
        initial = super().get_initial()
        initial["import_event"] = Event.objects.get(slug=self.kwargs["import_slug"])
        return initial

    def form_valid(self, form):
        import_types = ["import_categories", "import_requirements"]
        if apps.is_installed("AKDashboard"):
            import_types.append("import_buttons")

        for import_type in import_types:
            for import_obj in form.cleaned_data.get(import_type):
                # clone existing entry
                try:
                    import_obj.event = self.event
                    import_obj.pk = None
                    import_obj.save()
                    messages.add_message(self.request, messages.SUCCESS, _("Copied '%(obj)s'" % {'obj': import_obj}))
                except BaseException as e:
                    messages.add_message(self.request, messages.ERROR,
                                         _("Could not copy '%(obj)s' (%(error)s)" % {'obj': import_obj,
                                                                                     "error": str(e)}))
        return redirect("admin:new_event_wizard_activate", slug=self.event.slug)


class NewEventWizardActivateView(WizardViewMixin, UpdateView):
    model = Event
    template_name = "admin/AKModel/event_wizard/activate.html"
    form_class = NewEventWizardActivateForm
    wizard_step = 5

    def get_success_url(self):
        return reverse_lazy("admin:new_event_wizard_finish", kwargs={"slug": self.object.slug})


class NewEventWizardFinishView(WizardViewMixin, DetailView):
    model = Event
    template_name = "admin/AKModel/event_wizard/finish.html"
    wizard_step = 6
